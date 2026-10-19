"""Linux debootstrap backend. Only creates regular-file rootfs artifacts."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import uuid

from . import __version__


def run(argv, **kwargs):
    print("+ " + " ".join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def output_path(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("output must be a new directory; failed builds are retained for inspection")
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError("output ancestors must not be symlinks")
    if re.match(r"^/mnt/[a-z](?:/|$)", str(path)):
        raise ValueError("build on a native Linux filesystem, not a Windows /mnt drive; copy artifacts afterward")
    if not path.parent.is_dir():
        raise ValueError("output parent must already exist")
    return path


def host_status(debootstrap="debootstrap"):
    return {
        "platform": platform.system(), "machine": platform.machine(),
        "root": hasattr(os, "geteuid") and os.geteuid() == 0,
        "tools": {name: shutil.which(name) for name in (debootstrap, "chroot", "mke2fs", "tar", "xz")},
        "note": "Foreign architectures additionally require a working QEMU binfmt interpreter."
    }


def write(root, relative, content):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never follow a preexisting image symlink when writing configuration.
    if target.is_symlink():
        target.unlink()
    target.write_text(content, encoding="utf-8")


def configure(root, profile, ssh_key):
    write(root, "etc/hostname", profile["id"] + "\n")
    write(root, "etc/hosts", f"127.0.0.1 localhost\n127.0.1.1 {profile['id']}\n::1 localhost ip6-localhost ip6-loopback\n")
    write(root, "etc/fstab", "LABEL=debian-rootfs / ext4 defaults,noatime 0 1\n")
    suite = profile["suite"]
    write(root, "etc/apt/sources.list", (
        f"deb https://deb.debian.org/debian {suite} main\n"
        f"deb https://deb.debian.org/debian {suite}-updates main\n"
        f"deb https://security.debian.org/debian-security {suite}-security main\n"
    ))
    # Keep package services stopped while preparing the offline image.
    write(root, "usr/sbin/policy-rc.d", "#!/bin/sh\nexit 101\n")
    (root / "usr/sbin/policy-rc.d").chmod(0o755)
    run(["chroot", root, "apt-get", "-o", "APT::Update::Error-Mode=any", "update"])
    run(["chroot", root, "apt-get", "-o", "Dpkg::Use-Pty=0", "-y", "upgrade"],
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
    run(["chroot", root, "passwd", "-l", "root"])
    if ssh_key:
        run(["chroot", root, "useradd", "--create-home", "--shell", "/bin/bash", "debian"])
        write(root, "home/debian/.ssh/authorized_keys", ssh_key.rstrip() + "\n")
        (root / "home/debian/.ssh").chmod(0o700)
        (root / "home/debian/.ssh/authorized_keys").chmod(0o600)
        run(["chroot", root, "chown", "-R", "debian:debian", "/home/debian/.ssh"])
        write(root, "etc/ssh/sshd_config.d/10-debport.conf", "PasswordAuthentication no\nPermitRootLogin no\n")
    else:
        for unit in ("ssh.service", "ssh.socket"):
            target = root / "etc/systemd/system" / unit
            target.unlink(missing_ok=True)
            target.symlink_to("/dev/null")
    run(["chroot", root, "apt-get", "clean"])
    (root / "usr/sbin/policy-rc.d").unlink()
    for key in (root / "etc/ssh").glob("ssh_host_*"):
        key.unlink()
    # systemd assigns a fresh machine ID on first boot.
    (root / "etc/machine-id").unlink(missing_ok=True)
    dbus_id = root / "var/lib/dbus/machine-id"
    dbus_id.parent.mkdir(parents=True, exist_ok=True)
    dbus_id.unlink(missing_ok=True)
    dbus_id.symlink_to("/etc/machine-id")
    write(root, "etc/debport-image.json", json.dumps({
        "device": profile["id"], "status": "rootfs-only", "hardware_tested": False,
        "ssh": "public-key-only" if ssh_key else "disabled", "root_password": "locked"
    }, indent=2) + "\n")


def build(profile, output, size_mib=2048, debootstrap="debootstrap", debootstrap_dir=None,
          keyring=None, ssh_public_key=None):
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise ValueError("build-rootfs requires root in Linux (or WSL2); planning and import work on Windows")
    if size_mib < 768 or size_mib > 65536:
        raise ValueError("size-mib must be between 768 and 65536")
    output = output_path(output)
    host = host_status(debootstrap)
    missing = [name for name, executable in host["tools"].items() if not executable]
    if missing:
        raise ValueError("missing build tools: " + ", ".join(missing))
    ssh_key = None
    if ssh_public_key:
        ssh_key = Path(ssh_public_key).read_text(encoding="utf-8").strip()
        if "\n" in ssh_key or not re.fullmatch(r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) [A-Za-z0-9+/=]+(?: [^\r\n]*)?", ssh_key):
            raise ValueError("supply one OpenSSH public key, without authorized_keys options")
    output.mkdir(mode=0o755)
    root = output / "rootfs"
    record = {"builder": "debport", "version": __version__, "profile": profile,
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "status": "building", "hardware_tested": False, "host": host}
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    try:
        env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        if debootstrap_dir:
            env["DEBOOTSTRAP_DIR"] = str(Path(debootstrap_dir).resolve(strict=True))
        command = [debootstrap, "--variant=minbase", f"--arch={profile['architecture']}",
                   "--include=" + ",".join(profile["packages"])]
        if keyring:
            command.append("--keyring=" + str(Path(keyring).resolve(strict=True)))
        command.extend([profile["suite"], root, profile["mirror"]])
        run(command, env=env)
        configure(root, profile, ssh_key)
        with (output / "packages.tsv").open("w", encoding="utf-8") as packages:
            run(["chroot", root, "dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n"], stdout=packages)
        image = output / "rootfs.ext4"
        with image.open("xb") as stream:
            stream.truncate(size_mib * 1024 * 1024)
        filesystem_uuid = str(uuid.uuid4())
        run(["mke2fs", "-q", "-t", "ext4", "-F", "-b", "4096", "-L", "debian-rootfs",
             "-U", filesystem_uuid, "-O", "^orphan_file,^metadata_csum_seed", "-d", root, image])
        run(["tar", "--numeric-owner", "--xattrs", "--acls", "-C", root, "-cJf", output / "rootfs.tar.xz", "."])
        record.update(status="rootfs-built-not-device-boot-tested", filesystem_uuid=filesystem_uuid,
                      ssh="public-key-only" if ssh_key else "disabled",
                      finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        hashes = {}
        for name in ("rootfs.ext4", "rootfs.tar.xz", "packages.tsv"):
            with (output / name).open("rb") as stream:
                hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        record["sha256"] = hashes
        manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        with manifest.open("rb") as stream:
            hashes["manifest.json"] = hashlib.file_digest(stream, "sha256").hexdigest()
        (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8")
    except Exception as error:
        record.update(status="failed", error=str(error))
        manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        raise
    return output
