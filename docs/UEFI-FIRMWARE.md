# UEFI firmware design for NX769J

This is the design for `uefi-nx769j`, the Mu-Silicium platform package that
`./unixnu build firmware --uefi ../uefi-nx769j` builds. It states what the
package must contain, where every value comes from, and which values are still
open. The machine-readable part lives in [`board.toml`](../board.toml)
`[firmware]`; the files to place in the Mu-Silicium checkout are staged under
[`firmware/`](../firmware/).

Read it alongside [UEFI firmware](https://unixnu.com/porting/uefi-firmware),
which specifies the integration contract this design has to satisfy.

## What already exists

The starting point is not a blank port. Two things are already written and
verified on hardware, one generation back:

| Artifact | Where | Why it matters here |
| --- | --- | --- |
| `Platforms/ZTE/nx729jPkg/` | [`UniXNU/uefi-sheng`](https://github.com/UniXNU/uefi-sheng), branch `sheng` | A complete platform package for a nubia RedMagic — same brand, same vendor, one SoC generation back. Its `boot.img` reaches `fastboot boot OKAY` on hardware. |
| `Silicon/Qualcomm/LanaiPkg/` | same | Mu-Silicium's SM8650 SoC support. **This board is Lanai**, not Kailua. |
| `Resources/DTBs/nx729j.dtb` | same | The pattern for the firmware DTB `unixnu bootimg --dtb` consumes. |

`nx729jPkg` is `Platforms/Qualcomm/qrd8550Pkg` — the Pineapple QRD base board
this board is derived from — with board identity, framebuffer geometry and a
unique platform GUID substituted. `nx769jPkg` is the same derivation again.

### NX769J is a Lanai part

The SoC package is the one decision that is easy to get wrong, because Mu-Silicium
names SoC packages by Qualcomm platform codename rather than by `SM8xxx` part
number. The mapping is in each package's `*Pkg.dsc.inc`:

| Package | SMBIOS processor | Part numbers |
| --- | --- | --- |
| `WaipioPkg` | Snapdragon 8 Gen 1 | SM8450 |
| `KailuaPkg` | Snapdragon 8 Gen 2 | SM8550-AB / -AC |
| **`LanaiPkg`** | **Snapdragon 8 Gen 3** | **SM8650-AA / -Q-AA / -AB / -Q-AB / -AC** |
| `PalawanPkg` | Snapdragon 8s Gen 3 | SM8635 |
| `KaanapaliPkg` | Snapdragon 8 Elite Gen 5 | SM8850 |

Two independent sources agree that NX769J is Lanai:

1. The device's own firmware revisions, recorded in [`device-inputs.md`](../device-inputs.md):
   baseband `5.0.c3-00030-LANAI_GEN_PACK-1.46586.20` and trustzone
   `TZ.XF.5.0-07512.2-LANAIAAAAANAZT-1.46586.1`.
2. `LanaiPkg.dsc.inc` declares `SM8650-AA` and friends, and its GIC PCDs are
   `PcdGicDistributorBase|0x17100000` and `PcdGicRedistributorsBase|0x17180000`
   — the distributor and redistributor bases measured on this board.

So the DSC includes `LanaiPkg/LanaiPkg.dsc.inc`, not `KailuaPkg/`. Note that
`nx729jPkg` — being an SM8550 board — includes `KailuaPkg`; that single line is
the main SoC-level difference between the two packages.

## The package

```
uefi-nx769j/                        a Mu-Silicium checkout, branch nx769j
  Resources/
    Configs/nx769j.toml             NEW      firmware and boot image parameters
    DTBs/nx769j.dtb  nx769j.dts     NEW      firmware DTB, from the device
  Platforms/ZTE/nx769jPkg/          NEW
    nx769j.dsc
    nx769j.fdf
    nx769j.dec
    DeviceBuild.py
    Include/APRIORI.inc  DXE.inc  RAW.inc
    Library/MemoryMapLib/           NEW      the board memory map
    Library/ConfigurationMapLib/    NEW      the SoC configuration map
  Binaries/nx769j/QcomPkg/Drivers/  NEW      vendor DXE drivers, from the device
```

Everything not marked NEW comes from Mu-Silicium, either directly or by copying
`nx729jPkg` and renaming. `firmware/` in this repository holds the files that
are new or changed, ready to lift across.

## Values and where they come from

`Resources/Configs/nx769j.toml`:

| Key | Value | Source |
| --- | --- | --- |
| `boot_shim.requires_kernel_header` | `true` | Inherited from `nx729j.toml`. The ABL checks the ARM64 header at the start of the image. |
| `uefi_fd.base` | `0xA7100000` | Inherited. `sheng`, `qrd8550` and `nx729j` all use it; the UEFI stack PCD in the DSC sits at `0xA760D000`, just above a `0x300000` FD. |
| `uefi_fd.size` | `0x300000` | Inherited. Must equal the built FD size or `firmware.py` refuses it. |
| `boot_image_kernel.kernel_compression` | `"gzip"` | Inherited. BootShim and the FD are gzipped into the kernel field. |
| `boot_image_kernel.append_dtb` | `true` | Inherited. The firmware DTB is appended to the kernel field. |
| `boot_image.header_version` | `4` | **From `nx729j.toml`**, and this is the one place the sibling differs from `sheng`/`qrd8550`. NX769J is an Android 14 ABL board with `BOARD_BOOTIMG_HEADER_VERSION := 4`, exactly like nx729j. |

The remaining `boot_image` keys (`base`, `kernel_offset`, `tags_offset`,
`pagesize`) are not in `nx729j.toml`; `board.toml [bootimg.image]` supplies them.
See the header-version note there for why `unixnu bootimg` still writes a v0
header and what to do if the ABL rejects it.

`Platforms/ZTE/nx769jPkg/nx769j.dsc`, by class of value:

| Setting | Value | Source |
| --- | --- | --- |
| `PLATFORM_NAME`, `OUTPUT_DIRECTORY`, `FLASH_DEFINITION` | `nx769j` / `Build/nx769jPkg` / `nx729jPkg/nx769j.fdf` | Derived from `nx729jPkg`; `fd` in `board.toml` must match `OUTPUT_DIRECTORY`. |
| `PLATFORM_GUID` | new GUID | **Must be unique** — not nx729j's `DF09B1B0-…`. |
| `SOC_TYPE` | `2` | `LanaiPkg.dsc.inc`: `2` = `SM8650-AB`, Snapdragon 8 Gen 3 @ 3.30 GHz, 8 cores. See the open item below. |
| SoC include | `LanaiPkg/LanaiPkg.dsc.inc` | See above. |
| `PcdSystemMemoryBase` | `0x80000000` | **Measured** on this board — lowest System RAM range and `gunyah_hyp_region@80000000`. |
| `PcdCPUCoresStackBase` | `0xA760D000` | Inherited from nx729j/qrd8550. Above the FD at `0xA7100000`+`0x300000`. |
| `PcdCPUCorePrimaryStackSize` | `0x40000` | Inherited. |
| `PcdFrameBufferWidth/Height/ColorDepth` | `1116` / `2480` / `32` | **Measured** on this board from `card0-DSI-1`, and identical to what `nx729jPkg` uses. |
| `PcdSmbiosSystemManufacturer` | `"ZTE"` | nubia is ZTE's brand; matches `nx729jPkg`. |
| `PcdSmbiosSystemModel` / `…BoardModel` | `"RedMagic 9 Pro"` | Board name. |
| `PcdSmbiosSystemRetailModel` | `"nx769j"` | Codename. |
| `PcdSmbiosSystemRetailSku` | `"RedMagic_9_Pro_nx769j"` | Follows the `nx729jPkg` convention. |
| `PcdPlatformType` | `"LA"` | Inherited. |
| `MemoryMapLib`, `ConfigurationMapLib` | `nx769jPkg/Library/…` | Board specific; see below. |
| `AcpiTables.inf` | `nx769j/AcpiTables.inf` | Board specific. |

`Platforms/ZTE/nx769jPkg/nx769j.fdf` is `nx729j.fdf` with `nx729j` replaced by
`nx769j` throughout. It places `Include/APRIORI.inc`, `Include/DXE.inc` and
`Include/RAW.inc` in `FV.FvMain`, and pulls `QcomPkg/Extra.fdf.inc` and
`SiliciumPkg/Common.fdf.inc`. The commented-out `DeviceTreeBlob` block in the
FDF is left commented: this port appends the firmware DTB to the boot image
rather than embedding it in the FD.

## Required UniXNU integration

[Required integration](https://unixnu.com/porting/uefi-firmware#required-integration)
names six modules that must appear in the DSC `[Components]` **and** in the FDF
firmware volume:

| Module | Purpose |
| --- | --- |
| `UniXNUPkg/Application/UniXNU/UniXNU.inf` | Boot menu and configuration reader |
| `UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf` | Firmware boot option registration |
| `DarwinBootPkg/Driver/DarwinBoot.inf` | XNU loader |
| `UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf` | Publish the FDT initrd as a block device |
| `MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf` | Disk access for the filesystem driver |
| `FatPkg/EnhancedFatDxe/Fat.inf` | Expose the payload's FAT filesystem |

`nx729jPkg/Include/DXE.inc` already carries the last two, plus
`PartitionDxe` and `EnglishDxe` (the FAT driver's Unicode collation service).
The first four are **not** in the nx729j package and have to be added here. They
resolve through `PACKAGES_PATH`, not through the Mu-Silicium tree:

```
{uefi}:{uefi}/Platforms/ZTE:{tree}/package:{tree}/drivers/DarwinBoot:{edk2}:…
```

`{tree}/package` is this repository's `package/`, which supplies UniXNUPkg;
`{tree}/drivers/DarwinBoot` supplies DarwinBootPkg. That is what `board.toml
[firmware].packages` lists.

Two library mappings are required for the shared RAM-disk driver:

```ini
HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
```

`UniXNURamDiskDxe` must be **embedded in the firmware volume**, not loaded from
the payload: the payload is the thing it has to discover.

## Payload discovery path

The Android bootloader places the FAT payload in RAM and writes
`/chosen/linux,initrd-start` and `linux,initrd-end` into the firmware FDT, each
a 32- or 64-bit big-endian address. The range must hold complete 512-byte
sectors and stay reserved while UEFI runs.

Mu-Silicium SEC preserves the incoming FDT address as a `UINT64` in the
entry-argument HOB `DAEE82E6-8090-4E72-BFB9-78C13CD4E359`. `UniXNURamDiskDxe`
reads that handoff and publishes Block I/O; DiskIoDxe and FAT then expose
`EFI_SIMPLE_FILE_SYSTEM_PROTOCOL`, which lets UniXNU read
`\EFI\UniXNU\unixnu.toml` and list this board's entries from
[`package/unixnu.toml`](../package/unixnu.toml).

If the menu appears without the `xnu` entry, work through the five checks in
[payload discovery](https://unixnu.com/porting/uefi-firmware#payload-discovery),
starting with `boot/boot.json` reporting a nonzero `ramdisk_bytes`.

## Required services

| Service | Consumer |
| --- | --- |
| `EFI_GRAPHICS_OUTPUT_PROTOCOL` | UniXNU menu, DarwinBoot framebuffer handoff, XNU console |
| `EFI_SIMPLE_TEXT_IN_PROTOCOL` | UniXNU menu input |
| `EFI_SIMPLE_FILE_SYSTEM_PROTOCOL` | Configuration, payload and kernel files |
| `EFI_BLOCK_IO_PROTOCOL` | Userdata partition and block slices |
| `EFI_SERIAL_IO_PROTOCOL` | Logs on boards with a UART |
| `EFI_FIRMWARE_VOLUME2_PROTOCOL` | UniXNUDxe boot option registration |

The vendor DXE drivers in `Binaries/nx769j/` supply storage (`UFSDxe`) and the
platform services. Display comes from the GPU drivers; this board has Adreno 750
with no qualified driver, so **GOP is the display path and the firmware is what
publishes it** — see the display area of [`porting.toml`](../porting.toml).

## Vendor inputs

A Mu-Silicium port needs the vendor UEFI DXE drivers for the board. `nx729jPkg`
lists them from `Binaries/nx769j/QcomPkg/Drivers/…`, and the `Binaries`
submodule points at [`Project-Silicium/Device-Binaries`](https://github.com/Project-Silicium/Device-Binaries).

The set `nx729jPkg/Include/DXE.inc` uses, and therefore the set this board needs
an equivalent of:

| Driver | Role |
| --- | --- |
| `EnvDxe` | Environment and board configuration |
| `ShmBridgeDxe`, `TzDxe` (`ScmDxeCompat`, `TzDxeLA`) | TrustZone and shared-memory bridge |
| `ChipInfoDxe`, `PlatformInfoDxe`, `IPCCDxe` | SoC identity, platform info, inter-processor communication |
| `DALSYSDxe`, `HALIOMMUDxe`, `HWIODxe`, `I2CDxe`, `TLMMDxe` | Hardware access layer, IOMMU, bus access |
| `PmicDxe` (`PmicDxeLa`) | PMIC |
| `UFSDxe` | Internal storage — the block path XNU's root depends on |
| `CmdDbDxe`, `PwrUtilsDxe`, `RpmhDxe`, `NpaDxe`, `ULogDxe`, `VcsDxe` | RPMh power and logging |

These are extracted from the device's own firmware. [`proprietary-files.txt`](../proprietary-files.txt)
records the inventory and hashes; `scripts/extract-files.py` performs the
extraction. **They are not redistributable**, so `uefi-nx769j` cannot ship them —
they have to be extracted onto the machine doing the build.

`preflight = ["scripts/check-nx769j-firmware.py"]` exists to make a missing or
wrong vendor binary fail before EDK II runs rather than mid-build.

## Memory map

`Library/MemoryMapLib/MemoryMapLib.c` is the board's UEFI memory map and is the
most hardware-specific file in the package. The one staged here is nx729j's with
the identifiers renamed, and **it is not this board's map** — see the warning in
[`firmware/README.md`](../firmware/README.md).

Where the two agree, and where they do not:

| Region | nx729j's map | NX769J measured | |
| --- | --- | --- | --- |
| DRAM base | `0x80000000` | `0x80000000` | agrees — `PcdSystemMemoryBase` |
| Firmware volume | `0xA7100000` / `0x300000` | same | agrees — `uefi_fd.base` / `.size` |
| UEFI stack | `0xA760D000` / `0x40000` | same | agrees — `PcdCPUCoresStackBase` |
| `HYP` | `0x80000000` / `0x00A00000` | `0x80000000` / `0x00E00000` | **differs** — `gunyah_hyp_region` |
| Contiguous splash | `0xB8000000` / `0x2B00000` | `0xE3940000` / `0x2B00000` | **differs** — `splash_region`, `cont_splash_region` |
| `gpu_microcode_region` | absent | `0x9B09A000` / `0x2000` | **absent from the map** |
| `disp_rdump_region` | absent | `0xE3940000` / `0x800000` | **absent from the map** — a display ramdump window inside the splash region, from the public firmware dump |
| `ramoops` | absent | `0xD7E00000` / `0x200000` | **overlaps `TZApps Reserved`** at `0xD8800000` |
| XBL DT, AOP, SMEM, HW Fence, … | present | present | agree — all 49 reservations are now known |

The reservation list is complete. It comes from `vendor_boot.img` in the device's
flash package, whose `dtb` field holds six device trees; four are Pineapple
variants with byte-identical reservation sets. `scripts/extract-firmware-dtb.py`
prints them and the full table is in
[`device-inputs.md`](../device-inputs.md#fw-dtb).

What remains is the mapping. nx729j's table is a hand-built hybrid: the device
tree's fine-grained reservations grouped into coarser descriptors, plus UEFI's
own regions (`FD Reserved`, `UEFI Stack`, `SEC Heap`, `Sched Heap`, `FV Region`,
`DXE Heap`) that the device tree knows nothing about. Rebuild it from the
reservation list rather than editing it piecemeal — moving `Display Reserved`
alone would leave `0xB8000000..0xBAB00000` unaccounted, and the device tree
reserves nothing there.

**Do not boot the firmware until the map is rebuilt**: a map that reserves the
wrong ranges lets the firmware write over what the bootloader or TrustZone owns.

`Library/ConfigurationMapLib/ConfigurationMapLib.c` is the SoC configuration map
and is shared with every Lanai board; it should follow `nx729jPkg`'s.

The splash reservation is the one that bites: it is inside the DRAM window this
port hands to XNU (`[payload] dram_size = 0x80000000`), so the firmware map and
the ADT must both exclude it, or the framebuffer is overwritten under the boot
menu.

## Build

```sh
git clone https://github.com/UniXNU/uefi-sheng uefi-nx769j
cd uefi-nx769j && git checkout -b nx769j
# lift firmware/ across, then:
git submodule update --init --depth 1 -- \
  Common/Mu Common/Mu_OEM_Sample Silicium-ACPI \
  Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl

cd ../UniXNU
./unixnu defconfig nx769j_defconfig -D ../UniXNU-NX769J
./unixnu build firmware --uefi ../uefi-nx769j
```

`firmware.py` then runs the preflight, builds BaseTools if `GenFw` is absent,
applies `Resources/MuPatches/Gic-Spurious.patch` to the edk2 tree for the build
and reverts it afterwards, runs EDK II `build -p Platforms/ZTE/nx769jPkg/nx769j.dsc
-a AARCH64 -b <target> -t CLANGPDB`, and checks the output is exactly `0x300000`
bytes at `Build/nx769jPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`.

`SOURCE_DATE_EPOCH` is pinned to the Mu-Silicium commit time, so the same
sources give the same firmware.

## Verification

| Check | Method |
| --- | --- |
| Firmware volume size | `firmware.py` compares the output with `[uefi_fd] size` |
| Shim header | `unixnu bootimg` checks `ARM\x64` and the base and size fields |
| Boot image parts | `unixnu bootimg` unpacks the image and compares every part |
| Menu | The serial log contains `UNIXNU:` lines |
| Payload | The menu lists the `xnu` entry and DarwinBoot logs the handoff |
| Framebuffer | GOP geometry is `1116x2480x32`, matching the measured panel |

## Open items

Everything below is unresolved and stated as such rather than filled with a
plausible value.

| Item | Status | How to close it |
| --- | --- | --- |
| `SOC_TYPE` | Set to `2` (SM8650-AB, 3.30 GHz, 8 cores). The RedMagic 9 Pro is the 3.30 GHz bin and this board reports 8 CPUs (2×A520 + 5×A720 + 1×X4), so it is not a 6-core Q variant. | Read the prime core's max frequency from the device; `SOC_TYPE` `2` vs `4` distinguishes 3.30 from 3.40 GHz. |
| `PcdCPUCoresStackBase` | Inherited from `nx729jPkg`, and `MemoryMapLib` puts `UEFI Stack` at the same address. | Check it against the Lanai memory map and the splash reservation before the first boot. |
| **`MemoryMapLib`** | **Derived from `nx729jPkg`'s and not this board's.** Three conflicts are known — `HYP` size, `Display Reserved` address, and `TZApps Reserved` overlapping this board's `ramoops`. The data to rebuild it from is now complete. | Rebuild the table from the 49 reservations in [`device-inputs.md`](../device-inputs.md#fw-dtb), grouping them and adding UEFI's own regions. **Do not boot the firmware until this is done** — a wrong map lets it write over what the bootloader or TrustZone owns. |
| Firmware DTB | **Collected.** `vendor_boot.img` in the device's flash package carries six trees; the board matches the v2 pair by `qcom,msm-id`. | `scripts/extract-firmware-dtb.py --vendor-boot … --tree 2 -o Resources/DTBs/nx769j.dtb`. All four Pineapple trees have identical reservations, so the map does not depend on the choice. |
| Vendor DXE drivers | **All 20 recoverable.** `scripts/extract-uefi-drivers.py` pulls them out of `uefi.img`; nine carry a UI name different from the INF name and the script maps them. Not yet laid out under `Binaries/`. | Extract with `--out`, then give each module its EDK II INF wrapper per `Include/DXE.inc` and record the hashes in `proprietary-files.txt`. They cannot be redistributed, so every build machine runs the extraction. |
| UniXNU/DarwinBoot modules | **Added** to the DSC `[Components]`, the FDF volume, and the two library mappings. `./unixnu build package` builds `UniXNU.efi`, `UniXNUDxe.efi` and `UniXNURamDiskDxe.efi` on Linux with CLANGPDB, which is what proves those integration points resolve. | — |
| `PLATFORM_GUID` | Chosen: `F57D1EE0-603C-4EE3-AF74-1C995CE51AF3`, distinct from `nx729jPkg`'s. | — |
| `early_security_init` | Unset. `extract-ipsw-pins.py` used to emit AMFI's kmod stub address, which is not what the hook calls. | Reversing task; see the packaging area of [`porting.toml`](../porting.toml). |
| Boot on hardware | Not attempted. | Follow [bring-up](https://unixnu.com/porting/bring-up) and [`docs/FLASHING.md`](FLASHING.md). |

## Related

- [`docs/FLASHING.md`](FLASHING.md) — assembling and starting the boot image
- [`porting.toml`](../porting.toml) — the firmware area's scope, evidence and completion criteria
- [`README.md`](../README.md) — board overview and the non-destructive install path
