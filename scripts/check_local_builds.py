#!/usr/bin/env python3
"""Exercise real local builds with defaults and external supplied backend paths."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from fetch_tdm import ROOT, digest


def check(platform, backend):
    folder = {"macos-universal": "mac", "linux-x64": "linux", "windows-x64": "win"}[platform]
    windows = folder == "win"
    filename = "thymio-device-manager.exe" if windows else "thymio-device-manager"
    environment = dict(os.environ)
    for name in ("TDM_EXECUTABLE", "TDM_METADATA_DIR", "TdmExecutable", "TdmMetadataDir"):
        environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="tdm-local-") as temporary:
        temporary = Path(temporary)
        supplied = temporary / "external backends with spaces"
        supplied.mkdir()
        if windows:
            command = ["dotnet", "build", str(ROOT / "win/thymio-2-device-manager.csproj"), "-c", "Release"]
            output = ROOT / "win/build/bin/Release/net8.0-windows"
        else:
            output = temporary / "build"
            command = ["make", "-C", str(ROOT / folder), f"BUILD_DIR={output}"]
            if folder == "mac":
                output = output / "Thymio 2 Device Manager.app/Contents/MacOS"
        subprocess.run(command, env=environment, check=True)
        if digest(output / filename) != digest(ROOT / folder / filename):
            raise ValueError("Default local build did not preserve its backend")
        # Reuse the output directory while changing the source, including a
        # renamed external executable, so cached/stale copies cannot pass.
        for index, source in enumerate((backend, ROOT / folder / filename)):
            external = supplied / (f"custom backend {index}.exe" if windows else f"custom backend {index}")
            shutil.copy2(source, external)
            dlls = list(source.parent.glob("*.dll")) if windows else []
            for dll in dlls:
                shutil.copy2(dll, supplied / dll.name)
            override = f"-p:TdmExecutable={external}" if windows else f"TDM_EXECUTABLE={external}"
            subprocess.run([*command, override], env=environment, check=True)
            if digest(output / filename) != digest(source):
                raise ValueError("Supplied backend was modified or a stale copy was used")
            for dll in dlls:
                if digest(output / dll.name) != digest(dll):
                    raise ValueError(f"DLL was not copied: {dll.name}")
        if folder == "mac":
            unsigned = supplied / "unsigned local backend"
            shutil.copy2(backend, unsigned)
            subprocess.run(["codesign", "--remove-signature", str(unsigned)], check=True)
            subprocess.run([*command, f"TDM_EXECUTABLE={unsigned}"], env=environment, check=True)
            if digest(output / filename) != digest(unsigned):
                raise ValueError("Local build modified the unsigned supplied backend")
        for name, contents in (("missing backend", None), ("invalid backend", b"not an executable")):
            invalid = supplied / name
            if contents is not None:
                invalid.write_bytes(contents)
                invalid.chmod(0o755)
            override = f"-p:TdmExecutable={invalid}" if windows else f"TDM_EXECUTABLE={invalid}"
            result = subprocess.run([*command, override], env=environment, capture_output=True)
            if result.returncode == 0:
                raise ValueError(f"Build accepted {name}")
        print(f"{folder}: local defaults, overrides, backend switching and invalid paths verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["macos-universal", "windows-x64", "linux-x64"], required=True)
    parser.add_argument("--backend", type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.platform, args.backend.resolve())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
