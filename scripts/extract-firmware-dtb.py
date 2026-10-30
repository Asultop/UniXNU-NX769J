#!/usr/bin/env python3
"""Extract the firmware device tree from a vendor_boot image.

`unixnu bootimg --dtb` wants the device tree the Android bootloader hands to
UEFI. On this board that lives in the `dtb` field of `vendor_boot.img`, which is
a separate partition from `boot.img` and is not in the public firmware dump:
that repository has `dtbo.img` and its extracted overlays but no `vendor_boot`.

A flash package for the device has it. This script pulls the blob out, checks it
is a device tree, and writes it alongside a summary of what it declares --
the reservations, in particular, which is the input the UEFI memory map needs.

Read-only against the flash package: nothing outside --output is written.

Usage:
    scripts/extract-firmware-dtb.py --vendor-boot /path/to/vendor_boot.img \\
        [-o Resources/DTBs/nx769j.dtb] [--dts out.dts]
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

MAGIC = b'VNDRBOOT'
DTB_MAGIC = 0xd00dfeed

# struct vendor_boot_img_hdr_v3/v4. VENDOR_BOOT_NAME_SIZE is 16 bytes, not 64.
OFF_VERSION = 8
OFF_PAGE_SIZE = 12
OFF_VENDOR_RAMDISK_SIZE = 24
OFF_CMDLINE = 28
CMDLINE_SIZE = 2048
OFF_TAGS_ADDR = OFF_CMDLINE + CMDLINE_SIZE
OFF_NAME = OFF_TAGS_ADDR + 4
NAME_SIZE = 16
OFF_HEADER_SIZE = OFF_NAME + NAME_SIZE
OFF_DTB_SIZE = OFF_HEADER_SIZE + 4
OFF_DTB_ADDR = OFF_DTB_SIZE + 4


def trees(blob: bytes) -> list[tuple[int, bytes]]:
    """Split a DTB region into the device trees it carries.

    Qualcomm ships a set of them and the bootloader picks by board id, so the
    region is one tree after another, each starting with the FDT magic and each
    declaring its own total size. Walk that, rather than assuming one tree.
    """
    out, offset = [], 0
    while offset + 8 <= len(blob):
        magic, total = struct.unpack_from('>II', blob, offset)
        if magic != DTB_MAGIC or total < 8 or offset + total > len(blob):
            break
        out.append((offset, blob[offset:offset + total]))
        offset += total
    return out


FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def fail(message: str) -> None:
    raise SystemExit('extract-firmware-dtb: ' + message)


def walk(blob: bytes):
    """Yield (path, {property: bytes}) once per node of a flattened device tree."""
    (_, _, off_struct, off_strings) = struct.unpack_from('>5I', blob, 0)[:4]
    if off_struct >= len(blob) or off_strings >= len(blob):
        fail('implausible flattened device tree header offsets')
    stack: list[str] = []
    current: tuple[str, dict] | None = None
    at = off_struct

    while at + 4 <= len(blob):
        token, = struct.unpack_from('>I', blob, at)
        at += 4
        if token == FDT_BEGIN_NODE:
            if current is not None:
                yield current
            end = blob.index(b'\0', at)
            name = blob[at:end].decode('utf-8', 'replace')
            at = (end + 1 + 3) & ~3
            stack.append(name)
            current = ('/' + '/'.join(stack[1:]), {})
        elif token == FDT_END_NODE:
            if current is not None:
                yield current
                current = None
            if stack:
                stack.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from('>II', blob, at)
            at += 8
            value = blob[at:at + length]
            at = (at + length + 3) & ~3
            end = blob.index(b'\0', off_strings + nameoff)
            prop = blob[off_strings + nameoff:end].decode('utf-8', 'replace')
            if current is not None:
                current[1][prop] = value
        elif token == FDT_NOP:
            continue
        else:
            break
    if current is not None:
        yield current


def describe(blob: bytes) -> dict:
    """Model, compatible and the reserved-memory children of one tree."""
    model = compatible = ''
    reservations: list[str] = []
    in_reserved = False
    for path, props in walk(blob):
        if path == '/' and 'model' in props:
            model = props['model'].split(b'\0')[0].decode('utf-8', 'replace')
        if path == '/' and 'compatible' in props:
            compatible = ' '.join(x.decode('utf-8', 'replace')
                                  for x in props['compatible'].split(b'\0') if x)
        if path == '/reserved-memory':
            in_reserved = True
            continue
        if in_reserved and path.startswith('/reserved-memory/'):
            name = path.rsplit('/', 1)[1]
            if 'reg' in props:
                reg = props['reg']
                words = struct.unpack('>%dI' % (len(reg) // 4), reg[:len(reg) // 4 * 4])
                if len(words) >= 4:
                    reservations.append(f'{name:28s} 0x{(words[0] << 32) | words[1]:08x} / 0x{(words[2] << 32) | words[3]:x}')
                elif len(words) >= 2:
                    reservations.append(f'{name:28s} 0x{words[0]:08x} / 0x{words[1]:x}')
            elif 'size' in props:
                reservations.append(f'{name:28s} (size only, no reg)')
        elif in_reserved and not path.startswith('/reserved-memory'):
            in_reserved = False
    return {'model': model or '(none)', 'compatible': compatible or '(none)',
            'reservations': [f'reserved-memory  {r}' for r in reservations] or ['reserved-memory  (none)']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--vendor-boot', type=Path, required=True, help='the vendor_boot image')
    parser.add_argument('-o', '--output', type=Path, default=None, help='where to write the DTB')
    parser.add_argument('--dts', type=Path, default=None,
                        help='also decompile here, if dtc is on PATH')
    parser.add_argument('--tree', type=int, default=None,
                        help='which device tree of the set to write (default 0)')
    parser.add_argument('--replace', action='store_true', help='overwrite an existing output')
    args = parser.parse_args()

    if not args.vendor_boot.is_file():
        fail(f'{args.vendor_boot} not found')
    image = args.vendor_boot.read_bytes()
    if image[:8] != MAGIC:
        fail(f'{args.vendor_boot} is not a vendor boot image: magic {image[:8]!r}')

    version, = struct.unpack_from('<I', image, OFF_VERSION)
    page_size, = struct.unpack_from('<I', image, OFF_PAGE_SIZE)
    vendor_ramdisk_size, = struct.unpack_from('<I', image, OFF_VENDOR_RAMDISK_SIZE)
    header_size, dtb_size = struct.unpack_from('<II', image, OFF_HEADER_SIZE)
    dtb_addr, = struct.unpack_from('<Q', image, OFF_DTB_ADDR)
    name = image[OFF_NAME:OFF_NAME + NAME_SIZE].split(b'\0')[0].decode('utf-8', 'replace')
    cmdline = image[OFF_CMDLINE:OFF_CMDLINE + CMDLINE_SIZE].split(b'\0')[0].decode('utf-8', 'replace')

    if not page_size or page_size & (page_size - 1):
        fail(f'implausible page size {page_size:#x}')
    if not dtb_size:
        fail('this vendor boot image carries no device tree')

    # The device tree follows the vendor ramdisk, each part page aligned.
    offset = header_size
    offset = (offset + page_size - 1) & ~(page_size - 1)
    offset += vendor_ramdisk_size
    offset = (offset + page_size - 1) & ~(page_size - 1)

    if offset + dtb_size > len(image):
        fail(f'device tree at {offset:#x}+{dtb_size:#x} runs past the {len(image):#x}-byte image')
    region = image[offset:offset + dtb_size]

    print(f'vendor boot: {args.vendor_boot.name}')
    print(f'  header version  {version}')
    print(f'  page size       {page_size:#x}')
    print(f'  board name      {name or "(none)"}')
    print(f'  cmdline         {cmdline[:72]!r}' if cmdline else '  cmdline         (none)')
    print(f'  dtb region      {offset:#x} + {dtb_size:#x} ({dtb_size} bytes) -> load at {dtb_addr:#x}')

    found = trees(region)
    if not found:
        fail(f'no device tree found at {offset:#x}')
    if args.tree is not None and not 0 <= args.tree < len(found):
        fail(f'--tree {args.tree} is out of range; this image carries {len(found)}')
    if sum(len(blob) for _, blob in found) != dtb_size:
        print(f'  note            {dtb_size - sum(len(b) for _, b in found)} trailing bytes after the last tree')
    print(f'  device trees    {len(found)}')
    for index, (at, blob) in enumerate(found):
        summary = describe(blob)
        print(f'    [{index}] +{at:#x} {len(blob)} bytes  sha256 {hashlib.sha256(blob).hexdigest()[:16]}…')
        print(f'        model      {summary["model"]}')
        print(f'        compatible {summary["compatible"]}')
        for line in summary['reservations']:
            print(f'        {line}')

    if args.output is not None:
        chosen = found[args.tree][1] if args.tree is not None else found[0][1]
        if args.output.exists() and not args.replace:
            fail(f'{args.output} exists; pass --replace to overwrite it')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(chosen)
        print(f'  wrote           {args.output}  (tree {args.tree if args.tree is not None else 0})')

    if args.dts is not None:
        import shutil
        dtc = shutil.which('dtc')
        if dtc is None:
            print('  dtc not on PATH; skipping the decompile', file=sys.stderr)
        else:
            chosen = found[args.tree][1] if args.tree is not None else found[0][1]
            args.dts.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([dtc, '-I', 'dtb', '-O', 'dts', '-o', str(args.dts)],
                                    input=chosen, capture_output=True)
            if result.returncode and not args.dts.exists():
                fail('dtc failed:\n' + (result.stderr or b'').decode('utf-8', 'replace')[-2000:])
            print(f'  wrote           {args.dts}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
