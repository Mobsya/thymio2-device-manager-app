#!/usr/bin/env python3
"""Build a binary Debian package using the native dpkg dependency database."""

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from tdm import copy_metadata


PACKAGE = "thymio-2-device-manager"
LINUX_DIR = Path(__file__).resolve().parent.parent
ASSETS = LINUX_DIR / "packaging"
PODMAN_IMAGE = "localhost/thymio-deb-builder:ubuntu-26.04"


def run(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(
            f"{args[0]} failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def check_executable(path):
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Missing or non-executable binary: {path}")
    with path.open("rb") as source:
        header = source.read(20)
    if (
        len(header) != 20
        or header[:6] != b"\x7fELF\x02\x01"
        or header[6] != 1
        or header[7] not in (0, 3)
        or struct.unpack_from("<HH", header, 16) not in ((2, 62), (3, 62))
    ):
        raise ValueError(f"Expected an x86-64 Linux ELF executable: {path}")


def install(source, target, mode=0o644):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)


def build_with_podman(build_dir, backend, app_version, app_build, maintainer):
    if shutil.which("podman") is None:
        raise ValueError("Missing podman; install the Podman prerequisites in README.md")

    # Only dependencies go into the image. Sources are mounted at run time,
    # so ordinary source changes reuse the cached Ubuntu build environment.
    podman_build = [
        "podman", "build", "--platform=linux/amd64", "--pull=missing",
        "--force-rm", "--tag", PODMAN_IMAGE, "--file", str(ASSETS / "Containerfile"),
    ]
    if mirror := os.environ.get("UBUNTU_MIRROR"):
        podman_build.extend(["--build-arg", f"UBUNTU_MIRROR={mirror}"])
    subprocess.run([*podman_build, str(ASSETS)], check=True)

    output = build_dir / "podman"
    output.mkdir(parents=True, exist_ok=True)
    metadata_args = []
    if metadata := os.environ.get("TDM_METADATA_DIR"):
        metadata_args = ["--volume", f"{Path(metadata).resolve()}:/tdm-metadata:ro",
                         "--env", "TDM_METADATA_DIR=/tdm-metadata"]
    subprocess.run([
        "podman", "run", "--rm", "--platform=linux/amd64",
        "--userns=keep-id", "--network=none",
        "--volume", f"{LINUX_DIR.parent}:/src:ro",
        "--volume", f"{backend}:/backend:ro",
        "--volume", f"{output}:/output:rw",
        "--workdir", "/src/linux",
        "--env", f"APP_VERSION={app_version}",
        "--env", f"APP_BUILD={app_build}",
        "--env", f"DEB_MAINTAINER={maintainer}",
        *metadata_args,
        PODMAN_IMAGE, "make", "deb", "BUILD_DIR=/output", "TDM_EXECUTABLE=/backend",
    ], check=True)

    filename = f"{PACKAGE}_{app_version}-{app_build}_amd64.deb"
    os.replace(output / filename, build_dir / filename)
    print(f"Package: {build_dir / filename}")


def build_package(build_dir, backend, version, maintainer):
    launcher = build_dir / PACKAGE
    check_executable(launcher)
    build_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{PACKAGE}_{version}_amd64.deb"

    with tempfile.TemporaryDirectory(prefix="deb-", dir=build_dir) as temporary:
        work = Path(temporary)
        root = work / "package"
        private_bin = root / "usr/lib" / PACKAGE
        install(launcher, private_bin / PACKAGE, 0o755)
        install(backend, private_bin / "thymio-device-manager", 0o755)
        (root / "usr/bin").mkdir(parents=True)
        (root / "usr/bin" / PACKAGE).symlink_to(f"../lib/{PACKAGE}/{PACKAGE}")
        install(
            ASSETS / f"{PACKAGE}.desktop",
            root / "usr/share/applications" / f"{PACKAGE}.desktop",
        )
        install(
            LINUX_DIR.parent / "mac/icon.png",
            root / "usr/share/pixmaps" / f"{PACKAGE}.png",
        )
        install(
            ASSETS / "70-thymio-device-manager.rules",
            root / "usr/lib/udev/rules.d/70-thymio-device-manager.rules",
        )
        install(LINUX_DIR.parent / "README.md", root / "usr/share/doc" / PACKAGE / "README.md")
        if metadata := os.environ.get("TDM_METADATA_DIR"):
            copy_metadata(metadata, root / "usr/share/doc" / PACKAGE / "tdm")
        for script in ("postinst", "postrm"):
            install(ASSETS / script, root / "DEBIAN" / script, 0o755)

        run("desktop-file-validate", str(root / "usr/share/applications" / f"{PACKAGE}.desktop"))

        # dpkg-shlibdeps expects source metadata even for a binary-only package.
        # Keep that metadata in the temporary workspace, outside the payload.
        (work / "debian").mkdir()
        (work / "debian/control").write_text(
            f"Source: {PACKAGE}\n"
            "Section: education\n"
            "Priority: optional\n"
            f"Maintainer: {maintainer}\n\n"
            f"Package: {PACKAGE}\n"
            "Architecture: amd64\n"
            "Description: Desktop launcher for the Thymio Device Manager\n",
            encoding="utf-8",
        )
        dependencies = run(
            "dpkg-shlibdeps", "--warnings=1", "-O",
            f"-e{private_bin / PACKAGE}",
            f"-e{private_bin / 'thymio-device-manager'}",
            cwd=work,
        )
        # Missing symbols are warnings, not errors, in dpkg-shlibdeps. They
        # must prevent distributing a backend built against unavailable APIs.
        if any(
            "warning:" in line and "symbol" in line
            for line in dependencies.stderr.splitlines()
        ):
            raise ValueError(f"Dependency analysis reported warnings:\n{dependencies.stderr.strip()}")
        # Ubuntu's merged-/usr loader diversion can produce informational
        # dpkg-query warnings. Preserve these without treating them as missing
        # symbols; missing libraries/metadata already cause a nonzero exit.
        if dependencies.stderr:
            print(dependencies.stderr, end="", file=sys.stderr)
        dependency_lines = dependencies.stdout.strip().splitlines()
        if len(dependency_lines) != 1 or not dependency_lines[0].startswith("shlibs:Depends="):
            raise ValueError(f"Unexpected dependency output: {dependencies.stdout!r}")
        depends = dependency_lines[0].removeprefix("shlibs:Depends=")
        if not depends:
            raise ValueError("No shared-library dependencies were found")

        installed_size = sum(
            (path.stat().st_size + 1023) // 1024
            for path in (root / "usr").rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        (root / "DEBIAN/control").write_text(
            f"Package: {PACKAGE}\n"
            f"Version: {version}\n"
            "Architecture: amd64\n"
            "Section: education\n"
            "Priority: optional\n"
            f"Maintainer: {maintainer}\n"
            f"Depends: {depends}, udev, avahi-daemon\n"
            f"Installed-Size: {installed_size}\n"
            "Homepage: https://github.com/Mobsya/thymio2-device-manager\n"
            "Description: Desktop launcher for the Thymio Device Manager\n"
            " Tray application to start and stop the bundled Thymio Device Manager.\n"
            " Includes USB access rules for Thymio II robots and wireless dongles.\n",
            encoding="utf-8",
        )
        result = run("dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(work / filename))
        print(result.stdout, end="")
        os.replace(work / filename, build_dir / filename)
    print(f"Package: {build_dir / filename}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check prerequisites before compiling")
    mode.add_argument("--podman", action="store_true", help="build inside an Ubuntu 26.04 LTS Podman container")
    args = parser.parse_args()
    os.environ["LC_ALL"] = "C"
    os.umask(0o022)

    app_version = os.environ.get("APP_VERSION", (LINUX_DIR.parent / "VERSION.txt").read_text().strip())
    app_build = os.environ.get("APP_BUILD", "1")
    maintainer = os.environ.get("DEB_MAINTAINER", "")
    if (
        re.search(r"[\x00-\x1f\x7f]", maintainer)
        or not re.fullmatch(r"[^<>]+ <[^<>\s@]+@[^<>\s@]+>", maintainer)
    ):
        raise ValueError('Set DEB_MAINTAINER="Name <email>" to the release maintainer')
    # These values are also embedded in C string literals by the Makefile.
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+~\-]*", app_version):
        raise ValueError("APP_VERSION must start with a digit and use Debian version characters")
    if not re.fullmatch(r"[A-Za-z0-9.+~]+", app_build):
        raise ValueError("APP_BUILD must be a non-empty Debian revision (for example, 1)")
    version = f"{app_version}-{app_build}"
    backend = (LINUX_DIR / os.environ.get("TDM_EXECUTABLE", "thymio-device-manager")).resolve()
    build_dir = (LINUX_DIR / os.environ.get("BUILD_DIR", "build")).resolve()
    check_executable(backend)
    if metadata := os.environ.get("TDM_METADATA_DIR"):
        if not Path(metadata).is_dir():
            raise ValueError(f"Missing backend metadata directory: {metadata}")

    if args.podman:
        build_with_podman(build_dir, backend, app_version, app_build, maintainer)
        return

    for tool in ("dpkg", "dpkg-architecture", "dpkg-shlibdeps", "dpkg-deb", "desktop-file-validate"):
        if shutil.which(tool) is None:
            raise ValueError(f"Missing {tool}; install the Debian/Ubuntu packaging prerequisites in README.md")
    if (
        run("dpkg", "--print-architecture").stdout.strip() != "amd64"
        or run("dpkg-architecture", "-qDEB_HOST_ARCH").stdout.strip() != "amd64"
    ):
        raise ValueError("Debian packaging currently supports native amd64 builds only")
    run("dpkg", "--validate-version", version)
    if not args.check:
        build_package(build_dir, backend, version, maintainer)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"deb: {error}", file=sys.stderr)
        sys.exit(1)
