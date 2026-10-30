#!/usr/bin/env python3
"""Extract the DXE drivers out of a Qualcomm UEFI firmware volume.

`build firmware` needs twenty vendor UEFI DXE drivers under
`Binaries/nx769j/QcomPkg/Drivers/…`. They are not redistributable, so every
build machine collects them from the device's own firmware package. This script
does that collection from the image that carries them.

Qualcomm ships the UEFI firmware as an ELF with an EFI firmware volume embedded
in it. The volume is a sequence of FFS files; each carries a UI section holding
the driver name and a PE32 section holding the driver itself. The names are the
ones `Include/DXE.inc` refers to -- `EnvDxe`, `UFSDxe`, `RpmhDxe` and the rest
-- so extracting by name is what makes them match.

Read-only against the firmware image: nothing outside --out is written.

Usage:
    scripts/extract-uefi-drivers.py --image uefi.img            # list
    scripts/extract-uefi-drivers.py --image uefi.img --out DIR  # extract
"""
from __future__ import annotations

import argparse
import hashlib
import lzma
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
DEVICE = HERE.parents[1]

FVH = b'_FVH'


def efi_guid(text: str) -> bytes:
    """The on-disk layout: Data1/2/3 little endian, Data4 as written."""
    parts = text.split('-')
    return (struct.pack('<IHH', int(parts[0], 16), int(parts[1], 16), int(parts[2], 16))
            + bytes.fromhex(parts[3]) + bytes.fromhex(parts[4]))


# EFI_LZMA_CUSTOM_DECOMPRESS, and the gzip one this board also uses. Note the
# on-disk layout when reading a GUID out of a hex dump: Data1, Data2 and Data3
# are little endian, so `e91f301d79be5343…` is 1D301FE9-BE79-4353-… and not the
# other way round.
LZMA_CUSTOM_DECOMPRESS = efi_guid('EE4E5898-3914-4259-9D6E-DC7BD79403CF')
GZIP_CUSTOM_DECOMPRESS = efi_guid('1D301FE9-BE79-4353-91C2-D23BC959AE0C')

FFS_FILE_HEADER2 = 0x00  # size field 0xFFFFFF means a large-file header follows
SECTION_GUID_DEFINED = 0x02
SECTION_PE32 = 0x10
SECTION_TE = 0x12
SECTION_UI = 0x15
SECTION_VERSION = 0x16
SECTION_RAW = 0x19

# What board.toml [firmware] and Include/DXE.inc expect under Binaries/nx769j.
# The UI section names in the image do not always match the INF names the DSC
# refers to -- the INF is a wrapper written around the prebuilt module -- so a
# name that differs is mapped rather than guessed at by prefix.
UI_TO_INF = {
    'EnvDxeEnhanced': 'EnvDxe',
    'ChipInfo': 'ChipInfoDxe',
    'PlatformInfoDxeDriver': 'PlatformInfoDxe',
    'DALSys': 'DALSYSDxe',
    'HALIOMMU': 'HALIOMMUDxe',
    'HWIODxeDriver': 'HWIODxe',
    'I2C': 'I2CDxe',
    'DALTLMM': 'TLMMDxe',
    'PmicDxe': 'PmicDxeLa',
}
EXPECTED = (
    'EnvDxe', 'ShmBridgeDxeLA', 'ScmDxeCompat', 'TzDxeLA', 'ChipInfoDxe',
    'IPCCDxe', 'PlatformInfoDxe', 'DALSYSDxe', 'HALIOMMUDxe', 'HWIODxe',
    'I2CDxe', 'TLMMDxe', 'PmicDxeLa', 'UFSDxe', 'CmdDbDxe', 'PwrUtilsDxe',
    'RpmhDxe', 'NpaDxe', 'ULogDxe', 'VcsDxe',
)


def inf_name(ui: str) -> str:
    """The INF name the DSC uses, given the module's UI section name."""
    return UI_TO_INF.get(ui, ui)


def fail(message: str) -> None:
    raise SystemExit('extract-uefi-drivers: ' + message)


def align(value: int, to: int = 4) -> int:
    return (value + to - 1) & ~(to - 1)


def find_volume(image: bytes) -> tuple[int, int]:
    """Offset and length of the first EFI firmware volume in an image."""
    at = image.find(FVH)
    if at < 0:
        fail('no EFI firmware volume: the _FVH signature is absent')
    base = at - 40  # zero vector (16) + FvNameGuid (16) + FvLength (8)
    if base < 0:
        fail('the _FVH signature is too early in the image to be a volume header')
    length, = struct.unpack_from('<Q', image, base + 32)
    if length <= 0 or base + length > len(image):
        fail(f'implausible firmware volume length {length:#x} at {base:#x}')
    return base, length


def files(image: bytes, base: int, length: int):
    """Yield (offset, name GUID bytes, type, size, body) for each FFS file.

    Free space is erased flash -- 0xFF when erase polarity is set -- and can sit
    between files, so a run of it is skipped rather than taken as end of volume.
    """
    header_length, = struct.unpack_from('<H', image, base + 48)
    at = base + header_length
    end = base + length
    while at + 24 <= end:
        if image[at] == 0xFF:
            at += 1
            continue
        name = image[at:at + 16]
        if name == b'\0' * 16:
            break
        file_type = image[at + 18]
        size = int.from_bytes(image[at + 20:at + 23], 'little')
        header = 24
        if size == 0xFFFFFF:
            if at + 32 > end:
                break
            size, = struct.unpack_from('<Q', image, at + 24)
            header = 32
        if size < header or at + size > end or file_type not in range(0x01, 0x10):
            at += 8
            continue
        yield at, name, file_type, size, image[at + header:at + size]
        at = align(at + size, 8)


def ui_name(data: bytes) -> str:
    """UI sections are UTF-16LE; some vendors write ASCII."""
    try:
        return data.decode('utf-16-le').split('\0')[0]
    except UnicodeDecodeError:
        return data.split(b'\0')[0].decode('utf-8', 'replace')


def sections(body: bytes):
    """Yield (type, data) for each section of an FFS file body."""
    at = 0
    while at + 4 <= len(body):
        size = int.from_bytes(body[at:at + 3], 'little')
        section_type = body[at + 3]
        if size < 4 or at + size > len(body):
            break
        yield section_type, body[at + 4:at + size]
        at = align(at + size, 4)


def decompress(payload: bytes, section_guid: bytes) -> bytes | None:
    """Unwrap a GUID_DEFINED section, or return None if it is not readable."""
    import gzip
    attempts = [
        ('gzip', lambda: gzip.decompress(payload)),
        ('lzma', lambda: lzma.decompress(payload)),
    ]
    # The GUID says which, but the header bytes say it more reliably when a
    # vendor reuses one; try both and take the first that works.
    if section_guid == LZMA_CUSTOM_DECOMPRESS:
        attempts.reverse()
    for _, attempt in attempts:
        try:
            return attempt()
        except Exception:
            continue
    return None


def collect(image: bytes, base: int | None = None, length: int | None = None,
            depth: int = 0) -> list[dict]:
    """Every FFS file of a volume, descending into compressed nested volumes.

    Qualcomm ships the DXE drivers inside firmware volumes that are themselves
    LZMA-compressed sections of an outer volume, so a flat walk finds only the
    SEC and the platform configuration. `UEFI_LZMA_CUSTOM_DECOMPRESS` names the
    only compression this board uses.
    """
    if base is None or length is None:
        base, length = find_volume(image)
    out = []
    for offset, guid, file_type, size, body in files(image, base, length):
        name, payload, nested = '', b'', []
        for section_type, data in sections(body):
            if section_type == SECTION_UI:
                name = ui_name(data)
            elif section_type in (SECTION_PE32, SECTION_TE, SECTION_RAW) and not payload:
                payload = data
            elif section_type == SECTION_GUID_DEFINED and len(data) >= 20:
                section_guid = data[:16]
                data_offset, _ = struct.unpack_from('<HH', data, 16)
                if section_guid in (LZMA_CUSTOM_DECOMPRESS, GZIP_CUSTOM_DECOMPRESS) and data_offset >= 4:
                    inner = decompress(data[data_offset - 4:], section_guid)
                    if inner is None:
                        continue
                    if depth < 4:
                        # The decompressed block is not always the FV at offset
                        # zero -- this board prefixes it -- so locate the volume
                        # by its signature the way find_volume does.
                        mark = inner.find(FVH)
                        if mark >= 40:
                            inner_base = mark - 40
                            inner_length, = struct.unpack_from('<Q', inner, inner_base + 32)
                            if 0 < inner_length <= len(inner) - inner_base:
                                nested = collect(inner, inner_base, inner_length, depth + 1)
        out.append({'offset': offset, 'guid': guid.hex(), 'type': file_type,
                    'size': size, 'name': name, 'payload': payload, 'nested': nested})
    return out


def flatten(entries: list[dict]) -> list[dict]:
    for entry in entries:
        yield entry
        yield from flatten(entry['nested'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True,
                        help='the firmware image carrying the volume (for example uefi.img)')
    parser.add_argument('--out', type=Path, default=None,
                        help='write each driver here as <name>.efi')
    parser.add_argument('--require', action='store_true',
                        help='fail unless every expected driver is present')
    args = parser.parse_args()

    if not args.image.is_file():
        fail(f'{args.image} not found')
    image = args.image.read_bytes()
    outer = collect(image)
    entries = list(flatten(outer))
    base, length = find_volume(image)
    nested = len(entries) - len(outer)
    print(f'{args.image.name}: firmware volume at {base:#x}, {length:#x} bytes')
    print(f'  {len(entries)} FFS files ({len(outer)} outer, {nested} in nested volumes), '
          f'{sum(1 for e in entries if e["payload"])} with a body')

    named = {inf_name(e['name']): e for e in entries if e['name']}
    drivers = [e for e in entries if e['payload'] and e['name']]
    print(f'  {len(drivers)} named drivers')
    for e in sorted(drivers, key=lambda e: inf_name(e['name'])):
        shown = inf_name(e['name'])
        renamed = f'  (UI name {e["name"]})' if shown != e['name'] else ''
        marker = '' if shown in EXPECTED else '   (not one of the 20)'
        print(f'    {shown:22s} {len(e["payload"]):7d} bytes  type {e["type"]:#04x}{marker}{renamed}')

    found = [n for n in EXPECTED if n in named]
    missing = [n for n in EXPECTED if n not in named]
    print(f'\n  expected {len(EXPECTED)}: {len(found)} found, {len(missing)} missing')
    for n in missing:
        print(f'    missing {n}')
    if missing and args.require:
        fail(f'{len(missing)} expected driver(s) are not in this image')

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        for name in found:
            entry = named[name]
            target = args.out / f'{name}.efi'
            target.write_bytes(entry['payload'])
        print(f'  wrote {len(found)} drivers to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
