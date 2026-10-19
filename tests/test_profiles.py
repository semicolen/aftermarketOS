from pathlib import Path
import tempfile
import unittest

from debport.build import output_path
from debport.profiles import import_deviceinfo, load, validate


class DeviceProfiles(unittest.TestCase):
    def import_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deviceinfo"
            path.write_text(text, encoding="utf-8")
            return import_deviceinfo(path)

    def source(self, extra="", architecture="aarch64"):
        return (f'deviceinfo_format_version="0"\ndeviceinfo_arch="{architecture}"\n'
                'deviceinfo_name="Example tablet"\ndeviceinfo_codename="example-tablet"\n' + extra)

    def test_architecture_mapping_and_support_boundary(self):
        for source, target in (("aarch64", "arm64"), ("armv7", "armhf"), ("x86_64", "amd64")):
            profile = self.import_text(self.source(architecture=source))
            self.assertEqual(profile["architecture"], target)
            self.assertEqual(profile["status"], "rootfs-only")
            self.assertEqual(profile["hardware_support"], "metadata-only")

    def test_shell_expansions_and_commands_are_rejected(self):
        for line in ('deviceinfo_year="$(touch /tmp/example)"',
                     'deviceinfo_year="`uname`"', 'touch /tmp/example',
                     'deviceinfo_year="2020"; uname'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                self.import_text(self.source(line))

    def test_duplicate_unsupported_and_path_ids_rejected(self):
        for text in (self.source('deviceinfo_arch="armv7"'),
                     self.source(architecture="armhf"),
                     self.source().replace('"example-tablet"', '"../../unsafe"')):
            with self.assertRaises(ValueError):
                self.import_text(text)

    def test_real_device_boot_metadata_matches_checked_profile(self):
        upstream = Path(__file__).resolve().parents[1] / "upstream/2gta4l/port/device-samsung-gta4l/deviceinfo"
        if not upstream.exists():
            self.skipTest("optional upstream checkout not present")
        imported = import_deviceinfo(upstream)
        bundled = load(str(Path(__file__).resolve().parents[1] / "../aftermarketOS-gta4l/profiles/samsung-gta4l.json"))
        self.assertEqual(imported["boot"], bundled["boot"])
        self.assertEqual(imported["architecture"], bundled["architecture"])

    def test_package_arguments_cannot_be_options_or_shell(self):
        for package in ("--allow-unauthenticated", "bash;id", "../bash"):
            profile = load("generic-arm64")
            profile["packages"] = [package]
            with self.assertRaises(ValueError):
                validate(profile)

    def test_existing_output_and_windows_build_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                output_path(directory)
        # This path check is meaningful on Linux, where builds run.
        if Path("/").as_posix() == "/" and not Path("C:/").is_absolute():
            with self.assertRaises(ValueError):
                output_path("/mnt/c/debport-output")


if __name__ == "__main__":
    unittest.main()
