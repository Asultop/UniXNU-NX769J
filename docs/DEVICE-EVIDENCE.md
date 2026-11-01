# NX769J device evidence

Every entry here is one run on the unit itself, with the command that produced
the image, the image hashes and what the panel showed. The device is identified
by serial `FY233201030E` (chip unique id `0xEDE074DB`), firmware
`GEN_CN_NX769SV3.0.0B08MR6` and its Android 14 ABL.

The board has **no accessible serial console, no USB keyboard and no way to
export a log**, so the panel is the only output channel. Results are therefore
transcribed from photographs of the display and quoted verbatim below.

## Boot chain as observed

| Stage | Panel | Meaning |
| --- | --- | --- |
| firmware | logo, driver list | `SILICIUM_UEFI.fd` runs |
| menu | `version 0.1.0`, `config: \EFI\UniXNU\unixnu.toml` | UniXNU DXE driver runs |
| payload | `payload: initrd B3DFA000-B7FFF430 [EB58904D] fs 1` | the vendor_boot ramdisk mounts as FAT |
| entry | `1 UniXNU xnu` | the payload declares a boot entry |
| loader | `DARWINBOOT: hand-off to the kernel` | DarwinBoot receives the boot request |
| hand-off | top sixteenth of the panel green | `DarwinEnter` painted its marker, `ExitBootServices` succeeded |
| kernel | blue band below green | entry probe stage 1: kernel entry, MMU off |
| kernel | magenta band below blue | entry probe stage 2: just before the MMU is enabled |
| stall | nothing further | the kernel stops after the MMU switch |

A screen holding **green, blue and magenta with no red band and no panic text**
is the current state: the kernel runs, reaches the MMU switch and stops. An
early exception would have painted the top band red (the loader installs its own
`VBAR_EL1` before the branch and encodes ESR/ELR/FAR as bar codes).

## Error progression, in the order the runs happened

Each error named the next missing piece; none of them named the actual cause.

| Panel | Cause | Fix |
| --- | --- | --- |
| `'UniXNU' returned: Unsupported` | `xnu` entries resolve through `UNIXNU_LOADER_PROTOCOL` and nothing installed it | add `DarwinBootPkg/Driver/DarwinBoot.inf` to the firmware |
| `'UniXNU' returned: Out of resources` | the loader wants one contiguous conventional run of `owned_memory_size` | see the memory section |
| `Synchronous Exception ... Data abort: Synchronous external abort`, `FAR 0x00000001001D0000` | memory above 4 GiB was described in the map and the firmware cannot reach it | stop describing it |
| `no boot entry found` | built from a tree without the unconditional `ConnectAll`, so the initrd volume never got a `SimpleFileSystem` | see `package/UniXNUPkg/Library/UniXNULib/Main.c` |
| `NO WINDOW 80000000 BIG RUN 12845000 @ B8000000` | 2 GiB of owned memory against 310 MiB of free run | 512 MiB window, 764.8 MiB of conventional memory |

## Memory

| Map | Conventional | Hand-off |
| --- | --- | --- |
| DXE heap only (`Kernel` reserved) | 508.8 MiB, largest run 0x12845000 | `NO WINDOW 80000000 BIG RUN 12845000` for a 2 GiB window |
| `Kernel` as `Conv` | 764.8 MiB | `owned 20000000` allocated, hand-off reached |
| any map with memory above 4 GiB described | - | external abort at `FAR 0x1001D0000` |

`python3 scripts/check-memory-map.py --dtb ../uefi-nx769j/Resources/DTBs/nx769j.dtb
--map firmware/Platforms/ZTE/nx769jPkg/Library/MemoryMapLib/MemoryMapLib.c --board board.toml`
reports `64 descriptors, 37 fixed reservations, 37 covering one, 0 unexplained`.

The map has to be lifted into the Mu checkout before it reaches a build:
`cp -R firmware/. ../uefi-nx769j/`.

## Hand-off summary, read off the panel

```
HANDOFF kernel va FFFFFFF003DD0000 pa A81D0000
ENTRY pa AB7D6488 owned 20000000
WORDS 1400001E 00000000 00000000 00000000
VIDEO base E3940000 row 4464 1116x2480 32 bpp
```

`kernel va` is the lowest segment, `__PRELINK_TEXT`, not `__TEXT`: a prelinked
kernelcache is placed by segment, and the entry words read back from RAM match
the `kernel.macho` inside `payload.img` byte for byte, which is the check that the
load is correct. Comparing against `out/<device>/<os>/<config>/kernel/kernel.macho`
compares against an unpatched copy and misleads.

## Payload

- 64 MiB payload in `vendor_boot`'s `vendor_ramdisk` at ramdisk address `0x40000000`.
- The stock header places the ramdisk at `0x01000000` and the device tree at
  `0x01f00000`, a 15 MiB window, so the address has to move for a larger payload.
- The same payload as a `boot` ramdisk never reaches the menu.
- `mformat -F` produces a 4 MiB FAT32 volume with 8030 clusters that the firmware
  cannot mount (`fs 0`); `mformat -T 8192 -h 64 -s 32` produces FAT16 that mounts.
- Repacking the stock ramdisk reproduces the stock `vendor_boot_a` byte for byte.

## Kernel probes

`payload.adt.kernel_args` is `-v` only: `serial=3` selects the Apple SoC UART,
which this board does not expose, and removing it changes nothing (same three
bars, same stall).

The panic screen and a stage-4 reset probe share the zero padding after `_start`
and do not both fit: with a probe armed the panic screen needs `0xa1f` bytes
against `0x970` remaining, and `scripts/patch-xnu-entry-probe.py` refuses.

## Runs

| Date | boot.img sha256 (16) | vendor_boot | Panel result |
| --- | --- | --- | --- |
| 2026-10-31 | `b58be184180ec980` | 64 MiB payload | hand-off summary, green band |
| 2026-10-31 | `e9a9e712cbec09aa` | 64 MiB payload | green, blue, magenta, stall |
| 2026-10-31 | `d97fe9698e5d7632` | `vendor_boot_a_512m` | green, blue, magenta, stall |
| 2026-10-31 | `d97fe9698e5d7632` | payload without `serial=3` | unchanged |
| 2026-11-01 | `d97fe9698e5d7632` | `probe31`, reset 8 s after `_arm_vm_init` | pending |
