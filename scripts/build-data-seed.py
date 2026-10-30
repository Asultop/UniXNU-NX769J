#!/usr/bin/env python3
"""Build the writable Data seed for the payload from the iOS 16.5 OS volume.

`unixnu build payload --data-ramdisk` wants a packed ramdisk holding one APFS
volume with the initial `/private/var` of the target OS. UniXNU ships the two
halves of this as `scripts/prepare-owner-data-fixture.py` (make the volume) and
`scripts/seed-data-grow.py` (grow an existing one), but both are pinned to the
iPadOS 17.7.11 input the project is developed against: the first refuses any
whose `sbin/launchd` does not hash to that image's, and the second grows a
packed seed this port does not have. This does the whole thing for iOS 16.5 and
prints what it made.

Every step needs macOS: `hdiutil` formats and attaches the container and
`diskutil apfs resizeContainer` grows it. Run it there, or let
`.github/workflows/data-seed.yml` run it on a hosted macOS runner.

  1. a 32 MiB APFS volume named OwnerData, holding the OS volume's
     `private/var` without `staged_system_apps`, plus the empty directories the
     userland expects to find
  2. grown to --size-mib by extending the raw image and resizing the container,
     which leaves the volume and its UUID in place
  3. packed with DarwinBoot's DBRDISK1 writer, so only the non-zero pages travel

The volume UUID is new on every run, so it goes in the report and the kernel
takes whatever volume is on the seed window rather than looking one up.

Usage:
    scripts/build-data-seed.py --os-mount /Volumes/Image \\
        --output out/nx769j-data.dbr --size-mib 256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

MIB = 1024 * 1024
INITIAL_MIB = 32
# The userland expects these under the Data root even when the OS image has none.
EMPTY_DIRS = ('keybags', 'mobile/tmp', 'tmp', 'run')
# Copied into the seed but huge and replaceable on first boot.
SKIP_DIRS = ('staged_system_apps',)


def fail(message: str) -> None:
    raise SystemExit('build-data-seed: ' + message)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def packed_ramdisk(unixnu: Path | None):
    """DarwinBoot's DBRDISK1 writer, imported from the UniXNU checkout."""
    for root in (unixnu, Path('../UniXNU'), Path.home() / 'build/UniXNU'):
        if root is None:
            continue
        module = root / 'drivers/DarwinBoot/Test'
        if (module / 'packed_ramdisk.py').is_file():
            sys.path.insert(0, str(module))
            import packed_ramdisk
            return packed_ramdisk
    fail('packed_ramdisk.py not found; give --unixnu DIR pointing at a UniXNU checkout')


def check_mount(source: Path) -> int:
    """Refuse a mount that is not an OS volume, and report its launchd hash."""
    launchd = source / 'sbin/launchd'
    var = source / 'private/var'
    if not launchd.is_file():
        fail(f'{source} has no sbin/launchd; mount the IPSW OS volume, not another one')
    if not var.is_dir():
        fail(f'{source} has no private/var; there is no initial var tree to seed with')
    digest = hashlib.sha256(launchd.read_bytes()).hexdigest()
    entries = sum(1 for _ in var.rglob('*'))
    if entries < 2:
        fail(f'{var} holds {entries} entries, which is not an initial var tree')
    return digest


def copy_var(source: Path, target: Path) -> tuple[int, int]:
    """The OS volume's private/var, minus the directories that only bloat the seed."""
    count = total = 0
    for current, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        destination = target / Path(current).relative_to(source)
        destination.mkdir(parents=True, exist_ok=True)
        os.chmod(destination, stat.S_IMODE(Path(current).stat().st_mode))
        for name in list(dirs) + files:
            here, there = Path(current) / name, destination / name
            if here.is_symlink():
                there.symlink(os.readlink(here))
                if name in dirs:
                    dirs.remove(name)
            elif here.is_file():
                shutil.copy2(here, there)
                count += 1
                total += here.stat().st_size
    return count, total


def attached_device(attach: dict) -> str:
    return attach['system-entities'][0]['dev-entry']


def container_for(store: str) -> str:
    listing = plistlib.loads(subprocess.check_output(['diskutil', 'apfs', 'list', '-plist']))
    for entry in listing['Containers']:
        if any(p.get('DeviceIdentifier') == store for p in entry.get('PhysicalStores', [])):
            return entry['ContainerReference']
    fail(f'no APFS container found on the attached seed at {store}')


def verify_container(image: Path, size_mib: int) -> int:
    """The grown container must fill the image, within the 64 MiB slack APFS leaves."""
    header = image.open('rb').read(4096)
    if header[32:36] != b'NXSB':
        fail('the grown image does not start with an APFS container')
    block_size = int.from_bytes(header[36:40], 'little')
    blocks = int.from_bytes(header[40:48], 'little')
    target = size_mib * MIB
    if block_size != 4096 or blocks * block_size > target or blocks * block_size < target - 64 * MIB:
        fail(f'the container is {blocks * block_size} bytes, not the {target} asked for')
    return blocks * block_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--os-mount', type=Path, required=True,
                        help='the IPSW OS volume, mounted read-only')
    parser.add_argument('--output', type=Path, required=True,
                        help='where to write the packed seed (.dbr)')
    parser.add_argument('--size-mib', type=int, default=256,
                        help='Data container size in MiB (default 256, a RAM seed)')
    parser.add_argument('--unixnu', type=Path, default=None,
                        help='the UniXNU checkout holding drivers/DarwinBoot/Test/packed_ramdisk.py')
    parser.add_argument('--work', type=Path, default=None,
                        help='scratch directory (default: beside --output)')
    args = parser.parse_args()

    if args.size_mib < INITIAL_MIB:
        fail(f'--size-mib {args.size_mib} is below the {INITIAL_MIB} MiB the seed is created at')
    if args.output.exists():
        fail(f'{args.output} exists; this tool never overwrites a seed')

    source = args.os_mount.resolve()
    if not source.is_dir():
        fail(f'{source} is not a directory')
    launchd_hash = check_mount(source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = (args.work or args.output.parent / 'data-seed-work').resolve()
    work.mkdir(parents=True, exist_ok=True)
    image = work / 'owner-data.cdr'
    mount = work / 'mount'
    if image.exists():
        fail(f'{image} exists; clear the scratch directory first')
    packer = packed_ramdisk(args.unixnu.resolve() if args.unixnu else None)

    run('hdiutil', 'create', '-size', f'{INITIAL_MIB}m', '-layout', 'NONE', '-fs', 'APFS',
        '-volname', 'OwnerData', '-type', 'UDTO', str(image))
    mount.mkdir(exist_ok=True)
    attached = plistlib.loads(subprocess.check_output(
        ['hdiutil', 'attach', '-nobrowse', '-owners', 'off', '-mountpoint', str(mount),
         '-plist', str(image)]))
    device = attached_device(attached)
    volume_uuid = None
    try:
        volumes = [e for e in attached['system-entities'] if e.get('mount-point') == str(mount)]
        if len(volumes) != 1:
            fail('expected exactly one newly formatted scratch volume')
        info = plistlib.loads(subprocess.check_output(
            ['diskutil', 'info', '-plist', volumes[0]['dev-entry']]))
        volume_uuid = info['VolumeUUID']
        count, total = copy_var(source / 'private/var', mount)
        for name in EMPTY_DIRS:
            (mount / name).mkdir(parents=True, exist_ok=True)
        os.chmod(mount / 'tmp', 0o1777)
    finally:
        subprocess.run(['hdiutil', 'detach', device], check=True)

    # Grow: extend the raw image, then ask APFS to fill it. The volume and its
    # UUID survive, which is why this is a resize and not a reformat.
    with image.open('r+b') as handle:
        handle.truncate(args.size_mib * MIB)
    listing = run('hdiutil', 'attach', '-imagekey', 'diskimage-class=CRawDiskImage',
                  '-nomount', '-nobrowse', str(image))
    store = re.match(r'(/dev/disk\d+)', listing)
    if not store:
        fail(f'could not find the store device in {listing!r}')
    store = store.group(1).rsplit('/', 1)[1]
    try:
        run('diskutil', 'apfs', 'resizeContainer', container_for(store), '0')
    finally:
        subprocess.run(['hdiutil', 'detach', store, '-force'], capture_output=True)

    container_bytes = verify_container(image, args.size_mib)
    metadata = packer.pack(image, args.output)

    report = {
        'os_mount': str(source),
        'os_launchd_sha256': launchd_hash,
        'volume_uuid': volume_uuid,
        'size_mib': args.size_mib,
        'container_bytes': container_bytes,
        'files': count,
        'file_bytes': total,
        'skipped_dirs': list(SKIP_DIRS),
        'output': str(args.output),
        'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
        'output_bytes': args.output.stat().st_size,
        'hardware_tested': False,
        **metadata,
    }
    report_path = Path(str(args.output) + '.json')
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(f'\nbuild-data-seed: {args.output} ({args.output.stat().st_size} bytes)')
    print(f'  Data volume UUID {volume_uuid}')
    print(f'  pass it as: ./unixnu build payload --data-ramdisk {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
