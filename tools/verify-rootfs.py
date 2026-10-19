#!/usr/bin/env python3
"""Read-only artifact checks and emulated userspace smoke tests, never a boot test."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess


def capture(command):
    return subprocess.check_output(list(map(str, command)), text=True, stderr=subprocess.STDOUT).strip()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["status"] == "rootfs-built-not-device-boot-tested", "build did not complete")
    expected_files = {"rootfs.ext4", "rootfs.tar.xz", "packages.tsv", "manifest.json"}
    seen = set()
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name in expected_files and name not in seen, "unexpected or duplicate checksum path")
        seen.add(name)
        with (directory / name).open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == digest, f"checksum failed: {name}")
    require(seen == expected_files, "missing artifact checksum")
    archive_members = capture(["tar", "-tJf", directory / "rootfs.tar.xz"]).splitlines()
    require("./etc/debport-image.json" in archive_members and "./usr/bin/bash" in archive_members,
            "rootfs archive is missing expected contents")
    root = directory / "rootfs"
    architecture = manifest["profile"]["architecture"]
    with (root / "usr/bin/bash").open("rb") as stream:
        elf = stream.read(20)
    require(elf[:4] == b"\x7fELF", "bash is not ELF")
    machine = struct.unpack("<H" if elf[5] == 1 else ">H", elf[18:20])[0]
    require(machine == {"arm64": 183, "amd64": 62, "armhf": 40}[architecture], "wrong ELF architecture")
    actual = capture(["chroot", root, "dpkg", "--print-architecture"])
    require(actual == architecture, "wrong dpkg architecture")
    audit = capture(["chroot", root, "dpkg", "--audit"])
    require(not audit, f"unconfigured packages: {audit}")
    systemd = capture(["chroot", root, "/lib/systemd/systemd", "--version"])
    require(not os.path.lexists(root / "etc/machine-id"), "shared machine-id present")
    require(not list((root / "etc/ssh").glob("ssh_host_*")), "shared SSH host keys present")
    if manifest["ssh"] == "disabled":
        for unit in ("ssh.service", "ssh.socket"):
            require(os.readlink(root / "etc/systemd/system" / unit) == "/dev/null", "SSH not masked")
    filesystem_check = capture(["e2fsck", "-f", "-n", directory / "rootfs.ext4"])
    metadata = capture(["debugfs", "-R", "cat /etc/debport-image.json", directory / "rootfs.ext4"])
    # debugfs prints its version before the file contents.
    image_info = json.loads(metadata[metadata.index("{"):])
    require(image_info["device"] == manifest["profile"]["id"], "image profile mismatch")
    require(image_info["hardware_tested"] is False, "image misrepresents hardware support")
    return {
        "verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": "passed", "architecture": actual, "elf_machine": machine,
        "checksums": "passed", "rootfs_archive": "passed", "dpkg_audit": "clean", "systemd_version": systemd,
        "ext4_check": filesystem_check, "identity": image_info,
        "hardware_tested": False, "device_boot_tested": False,
        "scope": "QEMU userspace in a WSL chroot and filesystem-file checks; no device boot or Linux 4.19 test"
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = verify(args.directory)
    (args.directory / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
