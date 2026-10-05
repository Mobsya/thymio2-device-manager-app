#!/usr/bin/env python3
"""Validate and stage supplied backends. This module never downloads anything."""

import argparse
import os
from pathlib import Path
import shutil
import struct
import sys


MAC_CPUS = {0x01000007, 0x0100000C}  # x86_64, arm64


def mac_architectures(path):
    data = path.read_bytes()

    def thin(offset, size):
        if size < 32 or offset + size > len(data):
            raise ValueError("Truncated Mach-O executable")
        endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(data[offset:offset + 4])
        if not endian or struct.unpack_from(endian + "I", data, offset + 12)[0] != 2:
            raise ValueError("Expected a 64-bit Mach-O executable")
        return struct.unpack_from(endian + "I", data, offset + 4)[0]

    fat = {b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
           b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True)}
    if data[:4] not in fat:
        return {thin(0, len(data))}
    endian, wide = fat[data[:4]]
    if len(data) < 8:
        raise ValueError("Truncated universal Mach-O header")
    count = struct.unpack_from(endian + "I", data, 4)[0]
    stride = 32 if wide else 20
    if count not in (1, 2) or len(data) < 8 + stride * count:
        raise ValueError("Invalid universal Mach-O header")
    cpus = set()
    for index in range(count):
        pos = 8 + stride * index
        cpu = struct.unpack_from(endian + "I", data, pos)[0]
        offset, size = struct.unpack_from(endian + ("QQ" if wide else "II"), data, pos + 8)
        if offset < 8 + stride * count or thin(offset, size) != cpu or cpu in cpus:
            raise ValueError("Invalid universal Mach-O slice")
        cpus.add(cpu)
    return cpus


def validate_binary(path, target):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing backend executable: {path}")
    if target != "windows-x64" and os.name != "nt" and not os.access(path, os.X_OK):
        raise ValueError(f"Backend is not executable: {path}")
    with path.open("rb") as stream:
        header = stream.read(64)
        if target == "linux-x64":
            if (len(header) < 20 or header[:7] != b"\x7fELF\x02\x01\x01"
                    or struct.unpack_from("<HH", header, 16) not in ((2, 62), (3, 62))):
                raise ValueError(f"Expected an x86-64 Linux ELF executable: {path}")
        elif target == "windows-x64":
            if len(header) < 64 or header[:2] != b"MZ":
                raise ValueError(f"Expected a Windows x64 executable: {path}")
            stream.seek(struct.unpack_from("<I", header, 60)[0])
            pe = stream.read(26)
            if (len(pe) != 26 or pe[:6] != b"PE\0\0\x64\x86"
                    or struct.unpack_from("<H", pe, 24)[0] != 0x20B
                    or not struct.unpack_from("<H", pe, 22)[0] & 2
                    or struct.unpack_from("<H", pe, 22)[0] & 0x2000):
                raise ValueError(f"Expected a Windows x64 executable: {path}")
        elif target in ("macos", "macos-universal"):
            cpus = mac_architectures(path)
            if not cpus or not cpus <= MAC_CPUS or (target == "macos-universal" and cpus != MAC_CPUS):
                raise ValueError(f"Incorrect architectures for {target}: {path}")
        else:
            raise ValueError(f"Unknown platform: {target}")


def copy_metadata(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_dir():
        raise ValueError(f"Missing backend metadata directory: {source}")
    for item in source.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Unexpected metadata symlink: {item}")
        target = destination / item.relative_to(source)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            target.chmod(0o644)


def stage(executable, destination, target):
    executable, destination = Path(executable).resolve(), Path(destination).resolve()
    validate_binary(executable, target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if executable != destination:
        shutil.copyfile(executable, destination)
        destination.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=["macos", "macos-universal", "linux-x64", "windows-x64"])
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--destination", type=Path, help="Omit to validate only")
    parser.add_argument("--metadata-dir", default="")
    parser.add_argument("--metadata-destination", type=Path)
    args = parser.parse_args()
    if args.destination:
        stage(args.executable, args.destination, args.platform)
    else:
        validate_binary(args.executable, args.platform)
    if args.metadata_dir:
        if not args.metadata_destination:
            parser.error("--metadata-dir requires --metadata-destination")
        copy_metadata(args.metadata_dir, args.metadata_destination)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
