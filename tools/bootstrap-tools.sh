#!/bin/sh
# Extract Debian bootstrap tooling locally; do not install host packages.
set -eu
target=${1:?Usage: bootstrap-tools.sh /absolute/new/directory}
case "$target" in /*) ;; *) echo 'Use an absolute Linux path' >&2; exit 1 ;; esac
if [ -e "$target" ]; then
    echo 'Tool directory must not already exist' >&2
    exit 1
fi
mkdir -p "$target/downloads" "$target/sysroot"
target=$(cd "$target" && pwd -P)
cd "$target/downloads"
apt-get download debootstrap debian-archive-keyring
for package in ./*.deb; do
    dpkg-deb -x "$package" "$target/sysroot"
done
printf 'debootstrap: %s/sysroot/usr/sbin/debootstrap\n' "$target"
printf 'debootstrap-dir: %s/sysroot/usr/share/debootstrap\n' "$target"
printf 'keyring: %s/sysroot/usr/share/keyrings/debian-archive-keyring.gpg\n' "$target"
