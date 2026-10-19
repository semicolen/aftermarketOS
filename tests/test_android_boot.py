import gzip
from pathlib import Path
import struct
import unittest

from debport.android_boot import BootImage, image_id, newc_entry, read_newc, replace_initramfs


class AndroidBoot(unittest.TestCase):
    def fixture(self):
        header = bytearray(4096)
        header[:8] = b"ANDROID!"
        struct.pack_into("<10I", header, 8, 6, 0x8000, 7, 0x2000000, 0, 0xf00000, 0x1e00000, 4096, 2, 0)
        struct.pack_into("<IQI", header, 1632, 0, 0, 1660)
        struct.pack_into("<IQ", header, 1648, 3, 0x1f00000)
        return BootImage(bytes(header), b"kernel", b"ramdisk", b"dtb", 4096).pack()

    def test_roundtrip_and_payload_preservation(self):
        image = BootImage.parse(self.fixture())
        updated = BootImage.parse(image.pack(ramdisk=b"new ramdisk", cmdline="console=tty0"))
        self.assertEqual(updated.kernel, image.kernel)
        self.assertEqual(updated.dtb, image.dtb)
        self.assertEqual(updated.ramdisk, b"new ramdisk")
        self.assertEqual(updated.cmdline, "console=tty0")
        self.assertEqual(updated.header[48:64], image.header[48:64])

    def test_reject_corruption_and_truncation(self):
        image = self.fixture()
        corrupt = bytearray(image)
        corrupt[4096] ^= 1
        for candidate in (bytes(corrupt), image[:100], image[:-17]):
            with self.assertRaises(ValueError):
                BootImage.parse(candidate)

    def test_newc_preserves_unmodified_firmware(self):
        archive = newc_entry("init_2nd.sh", b"old", 0o100755, 1)
        archive += newc_entry("firmware.bin", b"\x00\xfffirmware", 0o100644, 2)
        archive += newc_entry("TRAILER!!!", b"", 0, 3)
        result = replace_initramfs(gzip.compress(archive), {"init_2nd.sh": (b"new", 0o100755)})
        entries = {name: (data, fields) for name, data, fields, _ in read_newc(gzip.decompress(result))}
        self.assertEqual(entries["firmware.bin"][0], b"\x00\xfffirmware")
        self.assertEqual(entries["init_2nd.sh"][0], b"new")
        self.assertEqual(entries["init_2nd.sh"][1][1], 0o100755)

    def test_reject_cpio_traversal_and_duplicate_names(self):
        with self.assertRaises(ValueError):
            newc_entry("../outside", b"bad", 0o100644, 1)
        archive = newc_entry("init", b"one", 0o100755, 1) + newc_entry("init", b"two", 0o100755, 2)
        archive += newc_entry("TRAILER!!!", b"", 0, 3)
        with self.assertRaises(ValueError):
            list(read_newc(archive))

    def test_actual_installed_boot_roundtrip_when_available(self):
        path = Path(__file__).resolve().parents[1] / "out/recovery-backup-20261018/boot.img"
        if not path.exists():
            self.skipTest("local device backup not present")
        original = path.read_bytes()
        parsed = BootImage.parse(original)
        repacked = parsed.pack()
        self.assertEqual(original[:len(repacked)], repacked)
        self.assertEqual(len(list(read_newc(gzip.decompress(parsed.ramdisk)))) > 100, True)


if __name__ == "__main__":
    unittest.main()
