"""Regression checks that never install a package or call the host's udev."""

import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ASSETS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_deb", ASSETS / "build-deb.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)
PACKAGE = packaging.PACKAGE
RULES = (
    '# Thymio II and wireless dongles: allow the active local desktop user USB access.\n'
    '\n'
    'SUBSYSTEM=="usb", ATTR{idVendor}=="0617", ATTR{idProduct}=="000a", TAG+="uaccess"\n'
    'SUBSYSTEM=="usb", ATTR{idVendor}=="0617", ATTR{idProduct}=="000c", TAG+="uaccess"\n'
)


def elf_file(path, machine=62):
    # A header fixture for validation/staging; it is never executed.
    path.write_bytes(b"\x7fELF\x02\x01\x01" + bytes(9) + struct.pack("<HH", 3, machine))
    path.chmod(0o755)
    return path


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.backend = elf_file(self.directory / "thymio-device-manager")
        self.launcher = elf_file(self.directory / PACKAGE)
        self.payload = self.directory / "payload"
        self.environment = {
            "APP_VERSION": "1.2.3",
            "APP_BUILD": "4",
            "DEB_MAINTAINER": "Test Maintainer <maintainer@example.org>",
            "BUILD_DIR": str(self.directory),
            "TDM_EXECUTABLE": str(self.backend),
        }

    def tool(self, *args, cwd=None):
        output = ""
        if args[0] in ("dpkg-architecture", "dpkg"):
            output = "amd64\n" if "--validate-version" not in args else ""
        elif args[0] == "dpkg-shlibdeps":
            self.assertTrue((cwd / "debian/control").is_file())
            self.assertEqual(sum(arg.startswith("-e") for arg in args), 2)
            output = "shlibs:Depends=libc6 (>= 2.38), libstdc++6 (>= 14), libavahi-client3\n"
        elif args[0] == "dpkg-deb":
            self.assertIn("--root-owner-group", args)
            if self.payload.exists():
                shutil.rmtree(self.payload)
            shutil.copytree(args[-2], self.payload, symlinks=True)
            # This is a staging test, not an archive-format or dpkg integration test.
            Path(args[-1]).write_bytes(b"test archive placeholder")
        elif args[0] != "desktop-file-validate":
            self.fail(f"Unexpected external command: {args}")
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    def invoke(self, overrides=None, tool=None, check=False, podman=False):
        with (
            patch.dict(os.environ, self.environment | (overrides or {})),
            patch("sys.argv", ["build-deb.py"] + (["--check"] if check else []) + (["--podman"] if podman else [])),
            patch.object(packaging.shutil, "which", return_value="/test/tool"),
            patch.object(packaging, "run", side_effect=tool or self.tool),
            patch("builtins.print"),
        ):
            packaging.main()

    def test_podman_build_uses_container_tools_and_preserves_host_binaries(self):
        original_launcher = self.launcher.read_bytes()
        original_backend = self.backend.read_bytes()
        commands = []

        def podman_command(args, check):
            self.assertTrue(check)
            commands.append(args)
            if args[1] == "run":
                (self.directory / "podman" / f"{PACKAGE}_1.2.3-4_amd64.deb").write_bytes(b"container output")
            return subprocess.CompletedProcess(args, 0)

        with patch.object(packaging.subprocess, "run", side_effect=podman_command):
            self.invoke(
                {"UBUNTU_MIRROR": "https://archive.ubuntu.com/ubuntu"},
                podman=True, tool=lambda *args, **kwargs: self.fail("Used host dpkg tools"),
            )

        self.assertEqual([command[:2] for command in commands], [["podman", "build"], ["podman", "run"]])
        self.assertIn("--platform=linux/amd64", commands[0])
        self.assertIn("UBUNTU_MIRROR=https://archive.ubuntu.com/ubuntu", commands[0])
        self.assertIn("--userns=keep-id", commands[1])
        self.assertIn("--network=none", commands[1])
        self.assertIn(f"{ASSETS.parent.parent}:/src:ro", commands[1])
        self.assertIn(f"{self.backend}:/backend:ro", commands[1])
        self.assertIn(f"{self.directory / 'podman'}:/output:rw", commands[1])
        self.assertIn("DEB_MAINTAINER=Test Maintainer <maintainer@example.org>", commands[1])
        self.assertIn("APP_VERSION=1.2.3", commands[1])
        self.assertIn("APP_BUILD=4", commands[1])
        self.assertEqual(self.launcher.read_bytes(), original_launcher)
        self.assertEqual(self.backend.read_bytes(), original_backend)
        self.assertEqual((self.directory / f"{PACKAGE}_1.2.3-4_amd64.deb").read_bytes(), b"container output")
        self.assertFalse((self.directory / "podman" / f"{PACKAGE}_1.2.3-4_amd64.deb").exists())

    def test_failed_container_does_not_publish_stale_output(self):
        filename = f"{PACKAGE}_1.2.3-4_amd64.deb"
        (self.directory / "podman").mkdir()
        (self.directory / "podman" / filename).write_bytes(b"stale build")
        (self.directory / filename).write_bytes(b"previous release")

        def fail_container(args, check):
            if args[1] == "run":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)

        with (
            patch.object(packaging.subprocess, "run", side_effect=fail_container),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            self.invoke(podman=True)
        self.assertEqual((self.directory / filename).read_bytes(), b"previous release")

    def test_payload_and_metadata(self):
        self.invoke()
        private_bin = self.payload / "usr/lib" / PACKAGE
        self.assertEqual((private_bin / "thymio-device-manager").read_bytes(), self.backend.read_bytes())
        self.assertEqual((private_bin / PACKAGE).read_bytes(), self.launcher.read_bytes())
        self.assertEqual((self.payload / "usr/bin" / PACKAGE).resolve(), private_bin / PACKAGE)
        self.assertEqual((self.payload / "usr/lib/udev/rules.d/70-thymio-device-manager.rules").read_text(), RULES)
        self.assertEqual(
            (self.payload / "usr/share/pixmaps" / f"{PACKAGE}.png").read_bytes(),
            (ASSETS.parent.parent / "mac/icon.png").read_bytes(),
        )
        control = (self.payload / "DEBIAN/control").read_text()
        self.assertIn("Version: 1.2.3-4\n", control)
        self.assertIn("Architecture: amd64\n", control)
        self.assertIn("Maintainer: Test Maintainer <maintainer@example.org>\n", control)
        self.assertIn("Depends: libc6 (>= 2.38), libstdc++6 (>= 14), libavahi-client3, udev, avahi-daemon\n", control)
        self.assertNotIn("debian", [entry.name for entry in self.payload.iterdir()])
        self.assertFalse((self.payload / "etc").exists())
        for path in self.payload.rglob("*"):
            if path.is_symlink():
                continue
            executable = path.parent == private_bin or path.name in ("postinst", "postrm")
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() or executable else 0o644)
        self.assertTrue((self.directory / f"{PACKAGE}_1.2.3-4_amd64.deb").is_file())
        self.assertEqual(list(self.directory.glob("deb-*")), [])

    def test_consecutive_package_versions(self):
        self.invoke()
        self.invoke({"APP_VERSION": "1.2.4", "APP_BUILD": "5"})
        self.assertIn("Version: 1.2.4-5\n", (self.payload / "DEBIAN/control").read_text())
        self.assertTrue((self.directory / f"{PACKAGE}_1.2.4-5_amd64.deb").is_file())

    def test_upstream_metadata_is_included(self):
        metadata = self.directory / "upstream metadata"
        metadata.mkdir()
        (metadata / "VERSION.txt").write_text("2.0.0\n")
        self.invoke({"TDM_METADATA_DIR": str(metadata)})
        self.assertEqual((self.payload / "usr/share/doc" / PACKAGE / "tdm/VERSION.txt").read_text(), "2.0.0\n")

    def test_preflight_does_not_require_a_built_launcher(self):
        self.launcher.unlink()
        self.invoke(check=True)
        self.assertFalse(self.payload.exists())

    def test_missing_backend_and_launcher(self):
        self.backend.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or non-executable"):
            self.invoke(check=True)
        elf_file(self.backend)
        self.launcher.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or non-executable"):
            self.invoke()

    def test_nonexecutable_backend(self):
        self.backend.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "Missing or non-executable"):
            self.invoke(check=True)

    def test_wrong_binary_architecture(self):
        for binary in (self.backend, self.launcher):
            with self.subTest(binary=binary.name):
                elf_file(binary, machine=183)
                with self.assertRaisesRegex(ValueError, "x86-64 Linux ELF"):
                    self.invoke()
                elf_file(binary)

    def test_wrong_host_architecture(self):
        def arm_tool(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout="arm64\n", stderr="")
        with self.assertRaisesRegex(ValueError, "native amd64"):
            self.invoke(tool=arm_tool, check=True)

    def test_invalid_metadata(self):
        for override in (
            {"DEB_MAINTAINER": ""},
            {"DEB_MAINTAINER": "Test <test@example.org>\nDepends: injected"},
            {"APP_BUILD": ""},
            {"APP_BUILD": '1"'},
            {"APP_VERSION": "invalid"},
            {"APP_VERSION": '1.0"'},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.invoke(override, check=True)

    def test_dependency_failures_never_create_an_archive(self):
        for diagnostic in ("missing library", "unresolved symbol", "empty dependencies"):
            def failed_dependencies(*args, **kwargs):
                if args[0] == "dpkg-shlibdeps":
                    if diagnostic == "missing library":
                        raise ValueError("dpkg-shlibdeps failed: missing library")
                    return subprocess.CompletedProcess(
                        args, 0,
                        stdout="shlibs:Depends=libc6\n" if diagnostic == "unresolved symbol" else "shlibs:Depends=\n",
                        stderr="dpkg-shlibdeps: warning: symbol missing_api used by binary found in none of the libraries\n" if diagnostic == "unresolved symbol" else "",
                    )
                return self.tool(*args, **kwargs)
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                self.invoke(tool=failed_dependencies)
            self.assertEqual(list(self.directory.glob("*.deb")), [])
            self.assertEqual(list(self.directory.glob("deb-*")), [])

    def test_loader_diversion_warning_does_not_block_packaging(self):
        def diverted_loader(*args, **kwargs):
            result = self.tool(*args, **kwargs)
            if args[0] == "dpkg-shlibdeps":
                result.stderr = (
                    "dpkg-shlibdeps: warning: diversions involved - output may be incorrect\n"
                    " diversion by libc6 from: /lib64/ld-linux-x86-64.so.2\n"
                )
            return result
        self.invoke(tool=diverted_loader)
        self.assertTrue((self.directory / f"{PACKAGE}_1.2.3-4_amd64.deb").is_file())


class MaintainerScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "calls"
        self.udev = self.directory / "udevadm"
        self.udev.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n'
            'case "$1" in\n'
            'control) exit "${RELOAD_STATUS:-0}";;\n'
            'trigger) exit "${TRIGGER_STATUS:-0}";;\n'
            'esac\n'
        )
        self.udev.chmod(0o755)

    def invoke(self, script, action, **environment):
        result = subprocess.run(
            ["/bin/sh", str(ASSETS / script), action],
            env={"PATH": str(self.directory), "CALL_LOG": str(self.log), **environment},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_configure_only_triggers_the_two_usb_products(self):
        expected = ["control --reload-rules"] + [
            "trigger --action=change --subsystem-match=usb "
            f"--attr-match=idVendor=0617 --attr-match=idProduct={product}"
            for product in ("000a", "000c")
        ]
        self.assertEqual(self.invoke("postinst", "configure"), expected)
        self.assertEqual(self.invoke("postinst", "configure"), expected * 2)

    def test_offline_udev_does_not_fail_configuration(self):
        self.assertEqual(self.invoke("postinst", "configure", RELOAD_STATUS="1"), ["control --reload-rules"])

    def test_trigger_failure_does_not_skip_the_second_product(self):
        self.assertEqual(len(self.invoke("postinst", "configure", TRIGGER_STATUS="1")), 3)

    def test_absent_udev_is_supported(self):
        self.udev.unlink()
        for script, action in (("postinst", "configure"), ("postrm", "remove"), ("postrm", "purge")):
            self.assertEqual(self.invoke(script, action), [])

    def test_removal_and_purge_reload_without_triggering(self):
        self.assertEqual(self.invoke("postrm", "remove"), ["control --reload-rules"])
        self.assertEqual(self.invoke("postrm", "purge", RELOAD_STATUS="1"), ["control --reload-rules"] * 2)

    def test_upgrade_cleanup_and_abort_do_not_reload_rules(self):
        for script, action in (("postrm", "upgrade"), ("postrm", "failed-upgrade"), ("postinst", "abort-upgrade")):
            self.assertEqual(self.invoke(script, action), [])


if __name__ == "__main__":
    unittest.main()
