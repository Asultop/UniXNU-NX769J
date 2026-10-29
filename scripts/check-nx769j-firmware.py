#!/usr/bin/env python3
"""Preflight the uefi-nx769j Mu-Silicium platform package before EDK II runs.

board.toml [firmware] lists this as a preflight script, so
`./unixnu build firmware --uefi <dir>` runs it first and fails here rather than
deep inside a C build. `--skip-preflight` bypasses it.

It checks three things, in the order they are likely to be wrong:

  1. the Mu-Silicium checkout and the platform files this board adds
  2. that the device configuration agrees with board.toml, since firmware.py
     reads uefi_fd.base and uefi_fd.size from one and bootimg.py reads the boot
     image parameters from the other
  3. the vendor DXE drivers, which are extracted from the device firmware and
     cannot be redistributed

The vendor set is allowed to be incomplete at this stage: missing drivers are
reported and the check still passes, because the firmware will not boot until
they are present but it will build, and a build is what this check gates. Use
--require-vendors to make them fatal.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

# DXE drivers nx729jPkg/Include/DXE.inc pulls from Binaries/<device>/QcomPkg.
# Each is an INF path relative to the Binaries root.
VENDOR_DRIVERS = (
    'QcomPkg/Drivers/EnvDxe/EnvDxe.inf',
    'QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf',
    'QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf',
    'QcomPkg/Drivers/TzDxe/TzDxeLA.inf',
    'QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf',
    'QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf',
    'QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf',
    'QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf',
    'QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf',
    'QcomPkg/Drivers/HWIODxe/HWIODxe.inf',
    'QcomPkg/Drivers/I2CDxe/I2CDxe.inf',
    'QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf',
    'QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf',
    'QcomPkg/Drivers/UFSDxe/UFSDxe.inf',
    'QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf',
    'QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf',
    'QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf',
    'QcomPkg/Drivers/NpaDxe/NpaDxe.inf',
    'QcomPkg/Drivers/ULogDxe/ULogDxe.inf',
    'QcomPkg/Drivers/VcsDxe/VcsDxe.inf',
)

# Modules the UniXNU boot chain needs, on top of the vendor set.
UNIXNU_MODULES = (
    'UniXNUPkg/Application/UniXNU/UniXNU.inf',
    'UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf',
    'UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf',
    'DarwinBootPkg/Driver/DarwinBoot.inf',
)

HERE = Path(__file__).resolve()


class Check:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.problems.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def parse_edk2_defines(path: Path) -> dict[str, str]:
    """The [Defines] block of a DSC, unquoted, comments stripped."""
    values: dict[str, str] = {}
    in_defines = False
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            in_defines = stripped.lower() == '[defines]'
            continue
        if not in_defines or not stripped or stripped.startswith('#'):
            continue
        stripped = stripped.split('#', 1)[0].strip()
        if '=' not in stripped:
            continue
        key, _, value = stripped.partition('=')
        values[key.strip()] = value.strip().strip('"')
    return values


def check_layout(uefi: Path, check: Check) -> Path | None:
    for required in ('Resources/Scripts/mkbootimg.py', 'BootShim/BootShim.S', 'Silicon/Silicium'):
        check.require((uefi / required).exists(), f'{uefi} is missing {required}; it is not a Mu-Silicium checkout')
    pkg = uefi / 'Platforms/ZTE/nx769jPkg'
    for required in ('nx769j.dsc', 'nx769j.fdf'):
        check.require((pkg / required).is_file(), f'{pkg / required} missing')
    for required in ('Library/MemoryMapLib/MemoryMapLib.inf', 'Library/ConfigurationMapLib/ConfigurationMapLib.inf'):
        check.require((pkg / required).is_file(), f'{pkg / required} missing')
    include = pkg / 'Include'
    for required in ('APRIORI.inc', 'DXE.inc', 'RAW.inc'):
        check.require((include / required).is_file(), f'{include / required} missing')
    return pkg if (pkg / 'nx769j.dsc').is_file() else None


def check_agreement(uefi: Path, device: Path, check: Check) -> None:
    config_path = uefi / 'Resources/Configs/nx769j.toml'
    board_path = device / 'board.toml'
    if not config_path.is_file():
        check.problems.append(f'{config_path} missing')
        return
    config = tomllib.loads(config_path.read_text(encoding='utf-8'))
    fd = config.get('uefi_fd', {})
    check.require(isinstance(fd.get('base'), int), 'uefi_fd.base is not an integer')
    check.require(isinstance(fd.get('size'), int), 'uefi_fd.size is not an integer')

    if not board_path.is_file():
        check.problems.append(f'{board_path} missing')
        return
    board = tomllib.loads(board_path.read_text(encoding='utf-8'))
    firmware = board.get('firmware', {})
    check.require(firmware.get('config') == 'nx769j', 'board.toml firmware.config is not nx769j')

    expected_fd = firmware.get('fd', '')
    match = re.match(r'Build/(\w+)/\{target\}_CLANGPDB/FV/SILICIUM_UEFI\.fd', expected_fd)
    check.require(bool(match), f'board.toml firmware.fd is not the Mu-Silicium FD layout: {expected_fd}')

    dsc = firmware.get('dsc', '')
    check.require(dsc == 'Platforms/ZTE/nx769jPkg/nx769j.dsc',
                  f'board.toml firmware.dsc is {dsc}, expected Platforms/ZTE/nx769jPkg/nx769j.dsc')

    if match and (uefi / dsc).is_file():
        text = (uefi / dsc).read_text(encoding='utf-8')
        defines = parse_edk2_defines(uefi / dsc)
        output = defines.get('OUTPUT_DIRECTORY', '')
        check.require(output == f'Build/{match.group(1)}',
                      f'DSC OUTPUT_DIRECTORY is {output}, which does not match board.toml firmware.fd')
        check.require(defines.get('FLASH_DEFINITION') == 'nx769jPkg/nx769j.fdf',
                      'DSC FLASH_DEFINITION is not nx769jPkg/nx769j.fdf')
        check.require(defines.get('PLATFORM_NAME') == 'nx769j', 'DSC PLATFORM_NAME is not nx769j')
        # The SoC package is the one line that is easy to get wrong: NX769J is
        # SM8650 "Lanai", not SM8550 "Kailua" like the board this package was
        # derived from. Match the include itself, not the bare name — a bare
        # substring also matches KailuaPkg misreadings and other package names.
        soc_include = re.search(r'^\s*!include\s+(\S*Pkg/\S+\.dsc\.inc)', text, re.MULTILINE)
        check.require(soc_include is not None, 'DSC has no SoC package include')
        if soc_include is not None:
            check.require(soc_include.group(1) == 'LanaiPkg/LanaiPkg.dsc.inc',
                          f'DSC includes {soc_include.group(1)}, expected LanaiPkg/LanaiPkg.dsc.inc')
        check.require(defines.get('SOC_TYPE') == '2',
                      f'DSC SOC_TYPE is {defines.get("SOC_TYPE")!r}, expected 2 (SM8650-AB)')

    # The Mu-Silicium config records what the ABL requires; board.toml records
    # what unixnu bootimg actually packs. bootimg.py merges DEFAULTS, then this
    # config, then board.toml [bootimg.image], so board.toml wins and the two
    # deliberately differ. Check both and say which one applies, rather than
    # asserting an equality that does not hold.
    header = config.get('boot_image', {}).get('header_version')
    check.require(header == 4, f'boot_image.header_version is {header}, expected 4 for the NX769J ABL')
    packed = board.get('bootimg', {}).get('image', {}).get('header_version')
    check.require(packed is not None, 'board.toml [bootimg.image] has no header_version')
    if header is not None and packed is not None and header != packed:
        check.note(f'boot image header: the ABL requires {header}, board.toml packs {packed} '
                   f'(board.toml wins; see its header-version note)')

    # The FD is compiled into BootShim and checked again when bootimg packs, so a
    # size that is not a whole number of 0x1000 blocks fails late and obscurely.
    size = fd.get('size')
    if isinstance(size, int):
        check.require(size > 0 and size % 0x1000 == 0, f'uefi_fd.size {size:#x} is not a whole number of 4 KiB blocks')


def check_modules(uefi: Path, pkg: Path, check: Check) -> None:
    dsc_text = (pkg / 'nx769j.dsc').read_text(encoding='utf-8') if (pkg / 'nx769j.dsc').is_file() else ''
    fdf_text = (pkg / 'nx769j.fdf').read_text(encoding='utf-8') if (pkg / 'nx769j.fdf').is_file() else ''
    for module in UNIXNU_MODULES:
        check.require(module in dsc_text, f'{module} is not in the DSC [Components]')
        check.require(module in fdf_text, f'{module} is not in the FDF firmware volume')
    for mapping in ('HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf',
                    'FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf'):
        check.require(mapping in dsc_text, f'{mapping} is not mapped; UniXNURamDiskDxe needs it')


def check_vendors(uefi: Path, check: Check, require: bool) -> None:
    root = uefi / 'Binaries/nx769j'
    present = [driver for driver in VENDOR_DRIVERS if (root / driver).is_file()]
    missing = [driver for driver in VENDOR_DRIVERS if driver not in present]
    check.note(f'vendor DXE drivers: {len(present)}/{len(VENDOR_DRIVERS)} present under {root}')
    for driver in missing:
        message = f'vendor driver missing: {driver}'
        if require:
            check.problems.append(message)
        else:
            check.note(f'  {message}')
    if missing and not require:
        check.note('  these come from the device firmware package and cannot be redistributed;')
        check.note('  run scripts/extract-files.py to collect them, then rerun with --require-vendors')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uefi', type=Path,
                        default=Path(os.environ.get('UNIXNU_UEFI') or ''),
                        help='the Mu-Silicium checkout (or UNIXNU_UEFI)')
    parser.add_argument('--device', type=Path, default=HERE.parents[1],
                        help='this device repository')
    parser.add_argument('--require-vendors', action='store_true',
                        help='fail when a vendor DXE driver is missing')
    args = parser.parse_args()

    uefi = args.uefi.expanduser()
    if not str(uefi) or not uefi.is_dir():
        print('check-nx769j-firmware: give the Mu-Silicium checkout with --uefi or UNIXNU_UEFI',
              file=sys.stderr)
        return 2

    check = Check()
    pkg = check_layout(uefi, check)
    if pkg is not None:
        check_agreement(uefi, args.device, check)
        check_modules(uefi, pkg, check)
    check_vendors(uefi, check, args.require_vendors)

    for note in check.notes:
        print(note)
    if check.problems:
        for problem in check.problems:
            print(f'check-nx769j-firmware: {problem}', file=sys.stderr)
        print(f'check-nx769j-firmware: {len(check.problems)} problem(s)', file=sys.stderr)
        return 1
    print(f'check-nx769j-firmware: {uefi} is consistent with board.toml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
