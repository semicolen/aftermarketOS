import argparse
import json
from pathlib import Path
import subprocess
import sys

from .build import build, host_status
from .profiles import PROFILE_DIR, import_deviceinfo, load


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental Debian builder; current outputs are rootfs-only, not tablet installers.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list bundled profiles")
    check = commands.add_parser("check-host", help="inspect Linux build requirements")
    check.add_argument("--debootstrap", default="debootstrap")
    plan = commands.add_parser("plan", help="show a profile and its outstanding device work")
    plan.add_argument("device")
    importer = commands.add_parser("import-device", help="import literal deviceinfo metadata without executing shell code")
    importer.add_argument("deviceinfo", type=Path)
    importer.add_argument("--output", type=Path, required=True)
    rootfs = commands.add_parser("build-rootfs", help="create a signed-archive Debian base tarball and ext4 image in Linux")
    rootfs.add_argument("device")
    rootfs.add_argument("--output", required=True)
    rootfs.add_argument("--size-mib", type=int, default=2048)
    rootfs.add_argument("--debootstrap", default="debootstrap")
    rootfs.add_argument("--debootstrap-dir")
    rootfs.add_argument("--keyring")
    rootfs.add_argument("--ssh-public-key", help="optional public key for user debian; otherwise SSH stays disabled")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for path in sorted(PROFILE_DIR.glob("*.json")):
                profile = load(str(path))
                print(f"{profile['id']}\t{profile['architecture']}\t{profile['status']}\t{profile['name']}")
        elif args.command == "check-host":
            print(json.dumps(host_status(args.debootstrap), indent=2))
        elif args.command == "plan":
            print(json.dumps(load(args.device), indent=2))
        elif args.command == "import-device":
            profile = import_deviceinfo(args.deviceinfo)
            with args.output.open("x", encoding="utf-8") as target:
                target.write(json.dumps(profile, indent=2) + "\n")
            print(f"Imported draft metadata: {args.output}")
        else:
            build(load(args.device), args.output, args.size_mib, args.debootstrap,
                  args.debootstrap_dir, args.keyring, args.ssh_public_key)
            print("Rootfs artifacts built. No device kernel, firmware, boot image or installer is included.")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"debport: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
