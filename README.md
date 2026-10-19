# aftermarketOS

Experimental Debian image tools for mobile devices, starting with a shared
Debian 13 backend and literal postmarketOS `deviceinfo` import. The Python CLI
currently keeps the name `debport`. This is a new backend, not a fork of
pmbootstrap. Device kernels, firmware, desktop adaptations and installers live
in separate device repositories.

The first working port is [Samsung Galaxy Tab A7 LTE SM-T505 / gta4l](https://github.com/semicolen/aftermarketOS-gta4l),
running Debian 13 and GNOME 48 with downstream Linux 4.19 and Turnip/Zink graphics.

## Inspect and import

Python 3.11+ is sufficient; the CLI has no Python runtime dependencies.

```sh
python3 -m debport list
python3 -m debport plan generic-arm64
python3 -m debport check-host
python3 -m debport import-device /path/to/deviceinfo --output device.json
python3 -m debport plan device.json
python3 -m unittest discover -s tests -v
```

Import reads literal double-quoted assignments without executing shell code.
It maps aarch64, armv7 and x86_64 to Debian architectures. Imported profiles
remain drafts: this does not convert APKBUILDs or establish hardware support.
The CLI accepts a JSON file path, so device profiles do not need to be copied
into the core package.

## Build a base filesystem

Use a Linux/WSL2 host with root, debootstrap, Debian archive keys, e2fsprogs,
GNU tar and xz. Cross builds need working QEMU binfmt for the target architecture.
Use native Linux storage under `/var/tmp` or `/home`; Windows-mounted rootfs
trees are rejected because they cannot preserve the required Linux semantics.

```sh
sudo python3 -m debport build-rootfs generic-arm64 --output /var/tmp/debian-base
# Or extract bootstrap tools locally, build, verify and export:
sudo sh tools/build-local.sh /var/tmp/debian-base-build generic-arm64
```

`tools/bootstrap-tools.sh` extracts debootstrap and Debian archive keys from
the host's APT repositories without installing host packages. Archive signature
verification stays enabled. Outputs include an ext4 image, rootfs tarball,
package inventory, provenance and SHA256 checksums. These are base filesystems;
they contain no device kernel, firmware, boot image or recovery installer.

Root is locked. Base images have no shared login password, and SSH is disabled
unless `--ssh-public-key` is supplied for the `debian` account. Device desktop
builds define their own local login policy; gta4l uses `user` / `147147`.

Builds use live Debian release repositories and record package versions.
Snapshot-pinned and bit-for-bit reproducible builds are not implemented.
See [design and boundaries](docs/design.md).

## Repository split

- This repository: reusable bootstrap/backend, profile importer, Android boot
  parser/repacker, base verification and tests.
- [aftermarketOS-gta4l](https://github.com/semicolen/aftermarketOS-gta4l): device
  profile, downstream services/patches, GNOME integration, firmware handling,
  recovery tooling and downloadable builds.

This is an independent experimental project, with no claim of affiliation
with Debian, postmarketOS or Nura.
