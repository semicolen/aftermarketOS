"""Checked Android v2 boot repacking and newc edits, without extracting paths."""

from dataclasses import dataclass
import gzip
import hashlib
from pathlib import PurePosixPath
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(value, boundary=4):
    return (value + boundary - 1) // boundary * boundary


def image_id(kernel, ramdisk, dtb):
    digest = hashlib.sha1()
    for payload in (kernel, ramdisk, b"", b"", dtb):
        digest.update(payload)
        digest.update(struct.pack("<I", len(payload)))
    return digest.digest() + bytes(12)


@dataclass
class BootImage:
    header: bytes
    kernel: bytes
    ramdisk: bytes
    dtb: bytes
    page_size: int

    @classmethod
    def parse(cls, data):
        require(data[:8] == b"ANDROID!" and len(data) >= 1660, "invalid Android boot header")
        kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = struct.unpack_from("<10I", data, 8)
        require(version == 2 and page in (2048, 4096, 8192, 16384), "only legacy v2 boot headers are supported")
        recovery_size, recovery_offset, header_size = struct.unpack_from("<IQI", data, 1632)
        require(not second_size and not recovery_size and not recovery_offset and header_size == 1660,
                "unsupported second-stage/recovery payload or header size")
        dtb_size, _ = struct.unpack_from("<IQ", data, 1648)
        require(kernel_size > 0 and ramdisk_size > 0 and dtb_size > 0, "missing boot payload")
        rd_offset = page + align(kernel_size, page)
        dtb_offset = rd_offset + align(ramdisk_size, page)
        end = dtb_offset + align(dtb_size, page)
        require(end + 16 <= len(data), "truncated boot image")
        require(data[end:end + 16] == b"SEANDROIDENFORCE", "Samsung trailer missing")
        result = cls(data[:page], data[page:page + kernel_size],
                     data[rd_offset:rd_offset + ramdisk_size], data[dtb_offset:dtb_offset + dtb_size], page)
        require(data[576:608] == image_id(result.kernel, result.ramdisk, result.dtb), "boot image ID mismatch")
        return result

    @property
    def cmdline(self):
        return (self.header[64:576] + self.header[608:1632]).split(b"\0", 1)[0].decode()

    def pack(self, ramdisk=None, cmdline=None):
        rd = self.ramdisk if ramdisk is None else ramdisk
        header = bytearray(self.header)
        struct.pack_into("<I", header, 16, len(rd))
        header[576:608] = image_id(self.kernel, rd, self.dtb)
        if cmdline is not None:
            encoded = cmdline.encode()
            require(len(encoded) <= 1535 and b"\0" not in encoded, "invalid kernel command line")
            header[64:576] = encoded[:512].ljust(512, b"\0")
            header[608:1632] = encoded[512:].ljust(1024, b"\0")
        pad = lambda payload: payload + bytes(align(len(payload), self.page_size) - len(payload))
        result = bytes(header) + pad(self.kernel) + pad(rd) + pad(self.dtb) + b"SEANDROIDENFORCE"
        require(len(result) < 100663296, "image does not fit SM-T505 boot partition")
        return result


def read_newc(data):
    offset = 0
    seen = set()
    while True:
        start = offset
        header = data[offset:offset + 110]
        require(len(header) == 110 and header[:6] == b"070701", "invalid newc header")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        size, name_size = fields[6], fields[11]
        require(name_size > 0 and offset + 110 + name_size <= len(data), "invalid cpio name length")
        offset += 110
        require(data[offset + name_size - 1] == 0, "unterminated cpio name")
        name = data[offset:offset + name_size - 1].decode()
        require(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts,
                "unsafe cpio path")
        offset = align(offset + name_size)
        require(offset + size <= len(data), "truncated cpio data")
        payload = data[offset:offset + size]
        offset = align(offset + size)
        if name == "TRAILER!!!":
            return
        require(name not in seen, "duplicate cpio path")
        seen.add(name)
        yield name, payload, fields, data[start:offset]


def newc_entry(name, payload, mode, inode):
    require(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts,
            "unsafe replacement cpio path")
    fields = [inode, mode, 0, 0, 1, 0, len(payload), 0, 0, 0, 0, len(name.encode()) + 1, 0]
    entry = b"070701" + b"".join(f"{value:08x}".encode() for value in fields) + name.encode() + b"\0"
    entry += bytes(-len(entry) % 4)
    entry += payload
    return entry + bytes(-len(entry) % 4)


def replace_initramfs(compressed, replacements):
    records = list(read_newc(gzip.decompress(compressed)))
    inode = max(record[2][0] for record in records) + 1
    result = b"".join(raw for name, _, _, raw in records if name not in replacements)
    for name, (payload, mode) in replacements.items():
        result += newc_entry(name, payload, mode, inode)
        inode += 1
    result += newc_entry("TRAILER!!!", b"", 0, inode)
    result += bytes(-len(result) % 512)
    return gzip.compress(result, compresslevel=6, mtime=0)
