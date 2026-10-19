"""Read declarative JSON profiles and import deviceinfo without executing it."""

import json
import re
from pathlib import Path

PROFILE_DIR = Path(__file__).with_name("profiles")
ARCHITECTURES = {"aarch64": "arm64", "x86_64": "amd64", "armv7": "armhf"}
TOKEN = re.compile(r"[a-z0-9][a-z0-9+.-]*\Z")
PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?\Z")


def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError("profile must be a JSON object")
    if profile.get("schema_version") != 1:
        raise ValueError("unsupported profile schema")
    for key in ("id", "suite"):
        if not isinstance(profile.get(key), str) or not TOKEN.fullmatch(profile[key]):
            raise ValueError(f"invalid {key}")
    if profile["suite"] not in ("bookworm", "trixie"):
        raise ValueError("this backend currently supports bookworm and trixie release repositories")
    if profile.get("architecture") not in ARCHITECTURES.values():
        raise ValueError("architecture has no supported Debian mapping")
    if not isinstance(profile.get("name"), str) or not profile["name"]:
        raise ValueError("profile needs a name")
    if profile.get("mirror") != "https://deb.debian.org/debian":
        raise ValueError("this backend currently requires the official Debian HTTPS mirror")
    packages = profile.get("packages")
    if not isinstance(packages, list) or not packages or any(
        not isinstance(p, str) or not PACKAGE.fullmatch(p) for p in packages
    ):
        raise ValueError("packages must be a nonempty list of Debian package names")
    if profile.get("status") != "rootfs-only":
        raise ValueError("this version only supports rootfs-only profiles")
    if not isinstance(profile.get("requirements"), list):
        raise ValueError("profile needs explicit outstanding hardware requirements")
    return profile


def load(identifier):
    candidate = Path(identifier)
    if not candidate.is_file():
        if not TOKEN.fullmatch(identifier):
            raise ValueError("use a known profile ID or an existing JSON file")
        candidate = PROFILE_DIR / f"{identifier}.json"
    return validate(json.loads(candidate.read_text(encoding="utf-8")))


def import_deviceinfo(path):
    values = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'(deviceinfo_[a-z0-9_]+)="([^"\\`$\x00-\x1f]*)"(?:\s+#.*)?', line)
        if not match:
            raise ValueError(f"line {number}: only literal double-quoted assignments are supported")
        key, value = match.groups()
        if key in values:
            raise ValueError(f"line {number}: duplicate {key}")
        values[key] = value
    if values.get("deviceinfo_format_version") != "0":
        raise ValueError("unsupported deviceinfo format version")
    arch = values.get("deviceinfo_arch")
    if arch not in ARCHITECTURES:
        raise ValueError(f"no Debian architecture mapping for {arch!r}")
    profile = json.loads((PROFILE_DIR / "generic-arm64.json").read_text(encoding="utf-8"))
    profile.update(id=values.get("deviceinfo_codename"), name=values.get("deviceinfo_name"),
                   architecture=ARCHITECTURES[arch], hardware_support="metadata-only")
    boot = {"format": "unconfigured"}
    if values.get("deviceinfo_generate_bootimg") == "true":
        boot["format"] = "android"
        for src, dest in (("header_version", "header_version"), ("flash_pagesize", "page_size")):
            if "deviceinfo_" + src in values:
                raw = values["deviceinfo_" + src]
                if not raw.isdecimal():
                    raise ValueError(f"invalid deviceinfo_{src}")
                boot[dest] = int(raw)
        for src, dest in (("flash_offset_base", "base"), ("flash_offset_kernel", "kernel_offset"),
                          ("flash_offset_ramdisk", "ramdisk_offset"), ("flash_offset_second", "second_offset"),
                          ("flash_offset_tags", "tags_offset"), ("flash_offset_dtb", "dtb_offset"),
                          ("dtb", "dtb"), ("kernel_cmdline", "kernel_cmdline"),
                          ("bootimg_custom_args", "custom_args")):
            if "deviceinfo_" + src in values:
                boot[dest] = values["deviceinfo_" + src]
        for src, dest in (("append_dtb", "append_dtb"),
                          ("bootimg_append_seandroidenforce", "append_seandroidenforce")):
            if "deviceinfo_" + src in values:
                raw = values["deviceinfo_" + src]
                if raw not in ("true", "false"):
                    raise ValueError(f"invalid deviceinfo_{src}")
                boot[dest] = raw == "true"
    profile["boot"] = boot
    profile["imported_deviceinfo"] = values
    profile["requirements"].append(
        "Imported metadata is a draft: review all boot fields; APKBUILDs, drivers and runtime services have not been converted."
    )
    return validate(profile)
