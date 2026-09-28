#!/usr/bin/env python3
"""Validate release versions and assemble/update a draft using the GitHub CLI."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from fetch_tdm import ROOT, UPSTREAM, digest, read_version


def versions(ref):
    version, backend = read_version(ROOT / "VERSION.txt"), read_version(ROOT / "TDM_VERSION")
    if ref.startswith("refs/tags/") and ref != f"refs/tags/v{version}":
        raise ValueError(f"Release tag must be v{version}, matching VERSION.txt")
    return version, backend


def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, text=True, capture_output=True)


def publish(directory, ref, repository, commit):
    version, backend = versions(ref)
    tag = f"v{version}"
    if ref != f"refs/tags/{tag}":
        raise ValueError("Draft releases require a matching wrapper tag")
    filenames = [f"thymio-2-device-manager-{version}-macos-universal.dmg",
                 f"thymio-2-device-manager-{version}-windows-x64.exe",
                 f"thymio-2-device-manager_{version}-1_amd64.deb"]
    files = [directory / name for name in filenames]
    for path in files:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing release output: {path}")

    existing = gh("api", f"repos/{repository}/releases/tags/{tag}", check=False)
    if existing.returncode:
        if "HTTP 404" not in existing.stderr:
            raise ValueError(f"Cannot inspect existing release: {existing.stderr}")
        release = None
    else:
        release = json.loads(existing.stdout)
        if not release["draft"]:
            raise ValueError(f"Refusing to overwrite published release {tag}")

    sums = directory / "SHA256SUMS"
    sums.write_text("".join(f"{digest(path)}  {path.name}\n" for path in files), encoding="utf-8")
    notes = directory / "release-notes.md"
    notes.write_text(
        f"Thymio 2 Device Manager {version}\n\n"
        f"Wrapper commit: `{commit}`\n\n"
        f"Bundled backend: [Thymio Device Manager v{backend}]({UPSTREAM}/releases/tag/v{backend}). "
        f"[Corresponding upstream source and build instructions]({UPSTREAM}/tree/v{backend}).\n\n"
        "- macOS 11+: universal Intel/Apple Silicon app, signed and notarized.\n"
        "- Windows 10/11 x64: self-contained executable; Bonjour service and applicable USB drivers are required.\n"
        "- Linux x64: Ubuntu 26.04 Debian package; install using APT to resolve dependencies.\n\n"
        "Before publishing this draft, test robot/dongle detection, About/version, and Quit on each platform. "
        "On Linux, also check installation, upgrade, removal, and USB access without sudo.\n",
        encoding="utf-8",
    )
    if release is None:
        gh("release", "create", tag, "--repo", repository, "--verify-tag", "--draft",
           "--title", f"Thymio 2 Device Manager {version}", "--notes-file", str(notes))
    gh("release", "upload", tag, *(str(path) for path in [*files, sums]),
       "--repo", repository, "--clobber")
    if release is not None:
        gh("release", "edit", tag, "--repo", repository, "--notes-file", str(notes))
    print(f"Draft ready: https://github.com/{repository}/releases/tag/{tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish"])
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
    parser.add_argument("--directory", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if args.action == "prepare":
        version, backend = versions(args.ref)
        output = f"version={version}\ntdm_version={backend}\n"
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.write(output)
        print(output, end="")
    else:
        publish(args.directory, args.ref, os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.stderr or str(error))
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
