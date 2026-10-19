#!/bin/sh
# Build, verify and export from persistent Linux storage in one invocation.
set -eu
work=${1:?Usage: build-local.sh /var/tmp/new-build-directory [device-id]}
device=${2:-generic-arm64}
case "$work" in /var/tmp/*|/home/*) ;; *) echo 'Use a new persistent Linux directory under /var/tmp or /home' >&2; exit 1 ;; esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export_dir="$repo/out/$(basename -- "$work")"
if [ -e "$work" ] || [ -e "$export_dir" ]; then
    echo 'Build and export directories must be new' >&2
    exit 1
fi
mkdir "$work"
sh "$repo/tools/bootstrap-tools.sh" "$work/tools"
cd "$repo"
python3 -m debport build-rootfs "$device" \
    --output "$work/build" \
    --debootstrap "$work/tools/sysroot/usr/sbin/debootstrap" \
    --debootstrap-dir "$work/tools/sysroot/usr/share/debootstrap" \
    --keyring "$work/tools/sysroot/usr/share/keyrings/debian-archive-keyring.gpg"
python3 "$repo/tools/verify-rootfs.py" "$work/build"
mkdir -p "$export_dir"
for artifact in rootfs.ext4 rootfs.tar.xz packages.tsv manifest.json SHA256SUMS verification.json; do
    cp --sparse=always "$work/build/$artifact" "$export_dir/"
done
printf '%s\n' 'Debian base rootfs only. No device kernel, firmware, boot image or installer. Not ready to flash.' > "$export_dir/READ-ME-FIRST.txt"
printf 'Verified artifacts exported to: %s\n' "$export_dir"
