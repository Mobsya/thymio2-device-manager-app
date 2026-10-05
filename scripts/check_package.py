#!/usr/bin/env python3
"""Smoke-check packaged executables without requiring a robot."""

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from fetch_tdm import digest
from tdm import validate_binary


def help_check(executable):
    result = subprocess.run([str(executable), "--help"], capture_output=True, text=True, timeout=20)
    if result.returncode != 1 or "--help" not in result.stdout + result.stderr:
        raise ValueError(f"Backend --help failed ({result.returncode}): {result.stdout}{result.stderr}")


def mac_check(app, version, signed):
    executable_dir = app / "Contents/MacOS"
    for name in ("thymio-device-manager", "thymio-2-device-manager"):
        validate_binary(executable_dir / name, "macos-universal")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info["CFBundleShortVersionString"] != version:
        raise ValueError("Incorrect app version")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    if signed:
        subprocess.run(["xcrun", "stapler", "validate", str(app)], check=True)
        subprocess.run(["spctl", "--assess", "--type", "execute", str(app)], check=True)
    help_check(executable_dir / "thymio-device-manager")
    launcher = subprocess.Popen([str(executable_dir / "thymio-2-device-manager")], start_new_session=True)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if launcher.poll() is not None:
                raise ValueError("Mac launcher exited during startup")
            listing = subprocess.check_output(["ps", "-axo", "ppid=,comm="], text=True)
            if any(line.strip().startswith(f"{launcher.pid} ") and line.rstrip().endswith("/thymio-device-manager")
                   for line in listing.splitlines()):
                print("Mac launcher started its bundled backend")
                return
            time.sleep(0.2)
        raise ValueError("Mac launcher did not start its bundled backend")
    finally:
        # Confine cleanup to the process group this test started.
        try:
            os.killpg(launcher.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            launcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(launcher.pid, signal.SIGKILL)
            launcher.wait()


def windows_check(executable, package):
    with tempfile.TemporaryDirectory(prefix="tdm single file ") as temporary:
        temporary = Path(temporary)
        copied = temporary / "thymio-2-device-manager.exe"
        shutil.copyfile(executable, copied)
        environment = dict(os.environ, DOTNET_BUNDLE_EXTRACT_BASE_DIR=str(temporary / "extracted"))
        result = subprocess.run([str(copied), "--check-backend"], cwd=temporary, env=environment,
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise ValueError(f"Packaged launcher cannot execute its backend: {result.stdout}{result.stderr}")
        extracted = list((temporary / "extracted").rglob("thymio-device-manager.exe"))
        if len(extracted) != 1:
            raise ValueError("Expected one extracted backend")
        for source in (package / "bin").iterdir():
            if source.name == "thymio-device-manager.exe" or source.suffix.lower() == ".dll":
                if digest(source) != digest(extracted[0].parent / source.name):
                    raise ValueError(f"Incorrect bundled backend file: {source.name}")
        for source in (package / "metadata").rglob("*"):
            if source.is_file() and digest(source) != digest(extracted[0].parent / "tdm" / source.relative_to(package / "metadata")):
                raise ValueError(f"Incorrect bundled metadata: {source.name}")
        print("Windows single-file backend, DLLs and metadata verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["macos", "windows", "backend"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--signed", action="store_true")
    parser.add_argument("--upstream", type=Path)
    args = parser.parse_args()
    if args.platform == "macos":
        mac_check(args.path.resolve(), args.version, args.signed)
    elif args.platform == "windows":
        if not args.upstream:
            parser.error("Windows checks require --upstream")
        windows_check(args.path.resolve(), args.upstream.resolve())
    else:
        help_check(args.path.resolve())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
