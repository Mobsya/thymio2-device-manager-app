"""Backend fetching/staging tests use fixtures and never contact GitHub."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_tdm
import tdm

ROOT = Path(__file__).resolve().parents[2]


def elf():
    return b"\x7fELF\x02\x01\x01" + bytes(9) + struct.pack("<HH", 3, 62) + bytes(44)


def pe():
    header = bytearray(90)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    header[64:70] = b"PE\0\0\x64\x86"
    struct.pack_into("<HH", header, 86, 2, 0x20B)
    return bytes(header)


def macho(cpu=0x01000007):
    return struct.pack("<IIIIIIII", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0)


def universal():
    return (struct.pack(">II", 0xCAFEBABE, 2)
            + struct.pack(">IIIII", 0x01000007, 0, 48, 32, 0)
            + struct.pack(">IIIII", 0x0100000C, 0, 80, 32, 0)
            + macho() + macho(0x0100000C))


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backend tests ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()

    def binary(self, name, content):
        path = self.directory / name
        path.write_bytes(content)
        path.chmod(0o755)
        return path

    def test_architectures(self):
        cases = [("linux-x64", elf()), ("windows-x64", pe()),
                 ("macos", macho()), ("macos-universal", universal())]
        for platform, content in cases:
            path = self.binary("backend", content)
            tdm.validate_binary(path, platform)
            wrong = "windows-x64" if platform != "windows-x64" else "linux-x64"
            with self.assertRaises(ValueError):
                tdm.validate_binary(path, wrong)
        with self.assertRaises(ValueError):
            tdm.validate_binary(self.binary("thin", macho()), "macos-universal")
        with self.assertRaises(ValueError):
            tdm.validate_binary(self.binary("fake fat", universal()[:48]), "macos-universal")

    def test_paths_with_spaces_and_switching_backend_preserve_bytes(self):
        destination = self.directory / "build folder" / "thymio-device-manager"
        for index in range(2):
            source = self.binary(f"custom backend {index}", elf() + bytes([index]))
            tdm.stage(source, destination, "linux-x64")
            self.assertEqual(destination.read_bytes(), source.read_bytes())
        with self.assertRaises(ValueError):
            tdm.stage(self.directory / "missing", destination, "linux-x64")
        with self.assertRaises(ValueError):
            tdm.stage(self.binary("wrong OS", pe()), destination, "linux-x64")
        self.assertEqual(destination.read_bytes(), elf() + b"\x01")

    @unittest.skipIf(os.name == "nt", "POSIX executable permissions")
    def test_executable_permission_is_required(self):
        source = self.binary("backend", elf())
        source.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "not executable"):
            tdm.validate_binary(source, "linux-x64")

    @unittest.skipIf(os.name == "nt", "GNU/POSIX Make interface")
    def test_linux_make_external_backend_and_failure(self):
        build_temp = tempfile.TemporaryDirectory(prefix="tdm-build-")
        self.addCleanup(build_temp.cleanup)
        build = Path(build_temp.name).resolve() / "output"
        source = self.binary("my backend", elf())
        command = ["make", "-C", str(ROOT / "linux"), "copy-tdm", f"BUILD_DIR={build}",
                   f"PYTHON={sys.executable}"]
        result = subprocess.run([*command, f"TDM_EXECUTABLE={source}"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((build / "thymio-device-manager").read_bytes(), source.read_bytes())
        result = subprocess.run([*command, f"TDM_EXECUTABLE={self.directory / 'missing'}"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_checksum_missing_duplicate_and_mismatch(self):
        archive = self.binary("package.zip", b"payload")
        checksum = hashlib.sha256(b"payload").hexdigest()
        sums = self.directory / "SHA256SUMS"
        sums.write_text(f"{checksum}  package.zip\n")
        self.assertEqual(fetch_tdm.verify_checksum(archive, sums), checksum)
        for content in ("", f"{'0' * 64}  package.zip\n", sums.read_text() * 2):
            sums.write_text(content)
            with self.assertRaises(ValueError):
                fetch_tdm.verify_checksum(archive, sums)

    def test_unsafe_archive_members(self):
        for name in ("../escaped", "/absolute", "root/../../escaped", "root/dir\\escaped", "root/C:escape", "root/dir./file", "root/NUL", "root/COM1.txt"):
            for extension in ("zip", "tar.gz"):
                with self.subTest(name=name, extension=extension):
                    archive = self.directory / f"bad.{extension}"
                    if extension == "zip":
                        with zipfile.ZipFile(archive, "w") as output:
                            output.writestr(name, b"bad")
                    else:
                        with tarfile.open(archive, "w:gz") as output:
                            entry = tarfile.TarInfo(name)
                            entry.size = 3
                            output.addfile(entry, io.BytesIO(b"bad"))
                    with self.assertRaises(ValueError):
                        fetch_tdm.extract_archive(archive, self.directory / "unpack", "root")

    def test_links_and_case_collisions_are_rejected(self):
        archive = self.directory / "bad.tar.gz"
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with tarfile.open(archive, "w:gz") as output:
                entry = tarfile.TarInfo("root/link")
                entry.type, entry.linkname = kind, "../outside"
                output.addfile(entry)
            with self.assertRaises(ValueError):
                fetch_tdm.extract_archive(archive, self.directory / "unpack", "root")
        archive = self.directory / "bad.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("root/BINARY", b"one")
            output.writestr("root/binary", b"two")
        with self.assertRaises(ValueError):
            fetch_tdm.extract_archive(archive, self.directory / "unpack", "root")

    def release_archive(self, platform, content=None):
        stem = f"thymio-device-manager-1.0.0-{platform}"
        source = self.directory / "archive source" / stem
        (source / "bin").mkdir(parents=True)
        windows = platform == "windows-x64"
        executable = source / "bin" / ("thymio-device-manager.exe" if windows else "thymio-device-manager")
        executable.write_bytes(content or (pe() if windows else universal() if platform == "macos-universal" else elf()))
        executable.chmod(0o755)
        if windows:
            (source / "bin/dnssd.dll").write_bytes(b"dependency fixture")
        for name in ("README.md", "PROVENANCE.md", "dependencies.lock.json"):
            (source / name).write_text("fixture")
        (source / "VERSION.txt").write_text("1.0.0\n")
        for name in ("licenses", "docs"):
            (source / name).mkdir()
            (source / name / "notice.txt").write_text("fixture notice")
        archive = self.directory / f"{stem}.{fetch_tdm.PLATFORMS[platform]}"
        if windows:
            with zipfile.ZipFile(archive, "w") as output:
                for item in source.rglob("*"):
                    if item.is_file():
                        output.write(item, item.relative_to(source.parent))
        else:
            with tarfile.open(archive, "w:gz") as output:
                output.add(source, arcname=stem)
        return archive

    def test_all_release_platforms_and_metadata(self):
        for platform in fetch_tdm.PLATFORMS:
            archive = self.release_archive(platform)

            def download(url, destination):
                if url.endswith("SHA256SUMS"):
                    destination.write_text(f"{fetch_tdm.digest(archive)}  {archive.name}\n")
                else:
                    self.assertTrue(url.endswith(archive.name))
                    shutil.copyfile(archive, destination)

            with patch.object(fetch_tdm, "download", side_effect=download):
                output = fetch_tdm.fetch("1.0.0", platform, self.directory / platform)
            info = json.loads((output / "metadata/UPSTREAM.json").read_text())
            self.assertEqual(info["tag"], "v1.0.0")
            self.assertEqual(info["sha256"], fetch_tdm.digest(archive))
            self.assertTrue((output / "metadata/licenses/notice.txt").exists())

    def test_download_failure_does_not_publish_staging_directory(self):
        output = self.directory / "result"
        with patch.object(fetch_tdm, "download", side_effect=ValueError("HTTP 404")):
            with self.assertRaisesRegex(ValueError, "404"):
                fetch_tdm.fetch("1.0.0", "linux-x64", output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.directory.glob("tdm-download-*")), [])

    def test_http_missing_release_error_is_actionable(self):
        with patch.object(fetch_tdm.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("url", 404, "not found", {}, None)):
            with self.assertRaisesRegex(ValueError, "Publish the pinned upstream release"):
                fetch_tdm.download("https://example.invalid/asset", self.directory / "download")

    def test_wrong_architecture_is_not_published(self):
        archive = self.release_archive("linux-x64", pe())

        def download(url, destination):
            if url.endswith("SHA256SUMS"):
                destination.write_text(f"{fetch_tdm.digest(archive)}  {archive.name}\n")
            else:
                shutil.copyfile(archive, destination)

        with patch.object(fetch_tdm, "download", side_effect=download):
            with self.assertRaisesRegex(ValueError, "Linux ELF"):
                fetch_tdm.fetch("1.0.0", "linux-x64", self.directory / "result")
        self.assertFalse((self.directory / "result").exists())


if __name__ == "__main__":
    unittest.main()
