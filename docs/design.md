# Design and feasibility

## Goal

Build Debian-based systems for multiple devices supported by postmarketOS,
starting with SM-T505, without duplicating the rootfs builder for every device.
The distro backend, device description, hardware packages and boot packager
must have separate interfaces. Reusing a profile does not establish hardware
support.

## Why this is more than switching package managers

[pmbootstrap](https://docs.postmarketos.org/pmbootstrap/installation.html)
uses Alpine chroots internally even when it runs on a Debian host. APKBUILDs,
Alpine dependencies, package hooks and postmarketOS initramfs integration do
not become Debian packages by changing the mirror. A general backend in a
pmbootstrap fork would need to address those assumptions throughout the tool.

This initial implementation isolates Debian rootfs creation first. Deviceinfo
import is the compatibility boundary. A future pmbootstrap integration could
call the same backend, but there is currently no such integration.

## Proposed interfaces

| Component | Shared responsibility | Current implementation |
| --- | --- | --- |
| Device profile | Debian architecture, source revisions, boot metadata, required adaptations | JSON profiles plus strict deviceinfo importer |
| Debian backend | Signed bootstrap, package installation, configuration, inventories | `debootstrap`, base tarball and ext4 image |
| Hardware package backend | Build device kernels, modules and userspace adaptations as `.deb` packages | Not implemented |
| Initramfs backend | Firmware/modules, root discovery, USB diagnostics and switch to Debian init | Experimental SM-T505 second stage using verified device inputs |
| Boot packager | Android boot headers, DTBs, U-Boot or other device-specific formats | Checked Samsung Android v2 repacking; other formats remain unimplemented |
| Installer packager | Device identity checks and target-specific installation | Experimental SM-T505 separate-filesystem installer and exact boot rollback |
| Validation | File checks, emulated userspace tests and physical-device tests | Profile/import tests; build evidence recorded separately |

The rootfs CLI does not flash devices. Its output is distinct from the separate
experimental device-test installer. Imported boot parameters are recorded for
review and are not interpolated into shell commands. See the
[SM-T505 boot-test notes](https://github.com/semicolen/aftermarketOS-gta4l/blob/main/docs/device-boot-test.md) for its narrower installation and
validation boundaries.

## First device: SM-T505

Reviewed `semicolen/2gta4l` branch `downstream`, revision
`ea1134e326e667d7c575670766dd9b9b5fd0077c` on 2026-10-18. Its kernel recipe pins
LineageOS `android_kernel_samsung_sm6115` revision
`381a5549ee66fa751f632ee0840f5631274209ee`, Linux 4.19.300 plus local patches.

The source repository documents postmarketOS hardware tests and contains
device-specific work for display, touch, WLAN, Bluetooth, audio, sensors,
modem/GPS and cameras. Those results are upstream reports, not Debian tests.
The public tree excludes matching locally extracted proprietary firmware and
the original builder's generated artifacts.

| Area | Reuse candidate | Debian work |
| --- | --- | --- |
| Kernel | Pinned sources, defconfig, vendor driver and compatibility patches | Rebuild or explicitly import verified kernel/DTBs and matching modules; audit configuration |
| Firmware | Extraction logic and file layout | Supply matching stock archives; create local packages and initramfs hooks |
| Boot | Android v2 parameters, DTB layout | Implement and verify Debian initramfs and boot-image assembly |
| Qualcomm startup | QRTR, mapper, subsystem holder and firmware helpers | Build for glibc; translate OpenRC supervision/dependencies to Debian services |
| GPU | KGSL Turnip and patched private Zink source recipes | Rebuild against Debian dependencies and glibc; validate compositor and app presentation |
| Audio/input/sensors | UCM files, udev rules, calibration and helpers | Package for Debian paths, service ordering and desktop versions |
| Camera | Isolated Android/Bionic runtime and native bridge | Preserve its isolation and rework packaging/integration; glibc alone does not replace Android vendor libraries |
| Recovery | Existing OrangeFox installation design | Adapt only after kernel/initramfs/rootfs integration is proven |

Alpine's compiled musl userspace packages cannot simply be installed into the
glibc Debian rootfs. Kernel modules depend on the exact kernel build rather
than the userspace libc; they still need matching version, configuration and
symbol metadata.

## Linux 4.19 and Debian 13

[Debian 13](https://www.debian.org/News/2025/20250809) ships systemd 257.
[The systemd v257 requirements](https://github.com/systemd/systemd/blob/v257/README)
list Linux 3.15 as the minimum baseline and Linux 5.4 as the recommended
baseline. Therefore 4.19 is not automatically excluded, but its kernel options,
backported APIs and each service's requirements need testing. Newer systemd
releases must be evaluated separately before any distro upgrade.

The upstream kernel already carries selected userspace API backports. Its
configuration also enables `CONFIG_FW_LOADER_USER_HELPER`, while systemd/udev's
documented configuration asks for it disabled. Determine whether the vendor
firmware path needs this facility before changing it. A published version
number alone is not a compatibility test.

## Milestones

1. **Reusable rootfs backend:** implemented and used for the first device;
   imports source metadata without executing it.
2. **Device kernel package:** package the exact SM-T505 kernel, modules and DTBs;
   require explicit artifact hashes and provenance.
3. **Minimal device boot:** implement initramfs/root discovery and Android v2
   packaging; reach Debian init and a diagnostic console on the physical tablet.
4. **Hardware packages:** move startup helpers to systemd with explicit ordering;
   bring up storage, touch, USB networking and WLAN before the desktop.
5. **User desktop:** rebuild the private GPU stack, then add GNOME/Phosh or Plasma
   and test login, updates, audio, rotation, power and application behavior.
6. **Second real device:** prove the interfaces with another port; implement its
   boot backend as necessary. Add distribution/repository and update integration
   after the device package formats are established.

Making Debian the base gives access to its package ecosystem. A user-friendly
tablet still needs an intentional desktop, onboarding, update behavior and
reliable hardware/power management; the base distribution does not supply
those device adaptations by itself.

Debian's userspace updates also do not maintain a custom Samsung kernel for
us. Device-kernel security fixes, firmware compatibility and rollback/update
behavior remain responsibilities of this project until suitable upstream
kernel support exists.

The first device now boots Debian GNOME with a Debian hardware package.
Device-specific implementation, physical validation and remaining power/cellular
work are maintained in aftermarketOS-gta4l; these design milestones describe the
shared interfaces and do not imply universal device support.
