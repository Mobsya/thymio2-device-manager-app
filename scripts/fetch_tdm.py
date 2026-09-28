#!/usr/bin/env python3
"""Explicitly download a pinned public TDM release; ordinary builds never call this."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile

from tdm import validate_binary


ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "https://github.com/Mobsya/thymio-device-manager"
PLATFORMS = {"macos-universal": "tar.gz", "linux-x64": "tar.gz", "windows-x64": "zip"}


def read_version(path):
    version = Path(path).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError(f"Expected a numeric major.minor.patch version in {path}")
    return version


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def download(url, destination):
    # Public release downloads need no token. In particular, do not forward a
    # repository token through GitHub's redirects to the asset storage service.
    request = urllib.request.Request(url, headers={"User-Agent": "thymio2-device-manager-builder"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except urllib.error.HTTPError as error:
        raise ValueError(f"Cannot download {url}: HTTP {error.code}. Publish the pinned upstream release and its assets first.") from error


def verify_checksum(archive, checksums):
    matches = []
    for line in checksums.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *](.+)", line)
        if match and match[2] == archive.name:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one SHA256SUMS entry for {archive.name}")
    actual = digest(archive)
    if actual != matches[0]:
        raise ValueError(f"SHA-256 mismatch for {archive.name}")
    return actual


def extract_archive(archive, destination, stem):
    """Extract regular files/directories only, beneath the expected package root."""
    seen = set()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

    def target(name):
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or path.parts[0] != stem
                or ".." in path.parts or "\\" in name or ":" in name
                or any(part.rstrip(" .") != part or part.split(".")[0].upper() in reserved
                       for part in path.parts)):
            raise ValueError(f"Unsafe archive path: {name}")
        # Case folding also catches collisions on Windows and standard macOS volumes.
        key = str(path).casefold()
        if key in seen:
            raise ValueError(f"Duplicate archive path: {name}")
        seen.add(key)
        return destination.joinpath(*path.parts)

    def write(path, source, executable):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            shutil.copyfileobj(source, output)
        path.chmod(0o755 if executable else 0o644)

    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                path = target(member.filename)
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f"Unsafe archive member: {member.filename}")
                if member.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    with source.open(member) as stream:
                        write(path, stream, mode & 0o111)
    else:
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                path = target(member.name)
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    with source.extractfile(member) as stream:
                        write(path, stream, member.mode & 0o111)
                else:
                    raise ValueError(f"Unsafe archive member: {member.name}")


def fetch(version, platform, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"Output already exists; choose a fresh staging directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stem = f"thymio-device-manager-{version}-{platform}"
    filename = f"{stem}.{PLATFORMS[platform]}"
    base = f"{UPSTREAM}/releases/download/v{version}"
    with tempfile.TemporaryDirectory(prefix="tdm-download-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        archive, checksums = temporary / filename, temporary / "SHA256SUMS"
        download(f"{base}/SHA256SUMS", checksums)
        download(f"{base}/{filename}", archive)
        checksum = verify_checksum(archive, checksums)
        extract_archive(archive, temporary / "unpacked", stem)
        package = temporary / "unpacked" / stem
        executable = package / "bin" / ("thymio-device-manager.exe" if platform == "windows-x64" else "thymio-device-manager")
        validate_binary(executable, platform)
        if platform == "windows-x64" and not (package / "bin/dnssd.dll").is_file():
            raise ValueError("Windows release is missing bin/dnssd.dll")
        if read_version(package / "VERSION.txt") != version:
            raise ValueError("Backend package VERSION.txt does not match the pinned version")
        metadata = package / "metadata"
        metadata.mkdir()
        for name in ("README.md", "VERSION.txt", "PROVENANCE.md", "dependencies.lock.json", "licenses", "docs"):
            item = package / name
            if item.is_dir():
                shutil.copytree(item, metadata / name)
            elif item.is_file():
                shutil.copyfile(item, metadata / name)
            else:
                raise ValueError(f"Upstream package is missing {name}")
        (metadata / "UPSTREAM.json").write_text(json.dumps({
            "repository": UPSTREAM, "tag": f"v{version}", "asset": filename,
            "sha256": checksum, "release": f"{UPSTREAM}/releases/tag/v{version}",
        }, indent=2) + "\n", encoding="utf-8")
        os.replace(package, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-file", type=Path, default=ROOT / "TDM_VERSION")
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(fetch(read_version(args.version_file), args.platform, args.output))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, urllib.error.URLError, tarfile.TarError, zipfile.BadZipFile) as error:
        sys.exit(str(error))
