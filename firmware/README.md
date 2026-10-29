# Staged Mu-Silicium files for `uefi-nx769j`

These are the files that are new or changed for this board in a Mu-Silicium
checkout. They are staged here so the firmware design is reviewable and so
creating the `uefi-nx769j` checkout is a copy rather than an authoring task.

Nothing here is built. Lift the tree across:

```sh
git clone https://github.com/UniXNU/uefi-sheng uefi-nx769j
cd uefi-nx769j && git checkout -b nx769j
cp -R ../UniXNU-NX769J/firmware/* .
git submodule update --init --depth 1 -- \
  Common/Mu Common/Mu_OEM_Sample Silicium-ACPI \
  Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl
```

`firmware/` is laid out as it lands in the checkout, so the copy is a plain
`cp -R`.

## Staged

Everything the package adds is here, so `cp -R firmware/* .` is the whole step.

| Staged path | Origin |
| --- | --- |
| `Resources/Configs/nx769j.toml` | derived from `nx729j.toml`, `header_version` 4 |
| `Platforms/ZTE/nx769jPkg/nx769j.dsc` | derived from `nx729jPkg/nx729j.dsc` |
| `Platforms/ZTE/nx769jPkg/nx769j.fdf` | derived from `nx729jPkg/nx729j.fdf` |
| `Platforms/ZTE/nx769jPkg/{nx769j.dec,DeviceBuild.py}` | `nx729jPkg`'s, renamed |
| `Platforms/ZTE/nx769jPkg/Include/{APRIORI,DXE,RAW}.inc` | `nx729jPkg/Include/`'s, with the `Binaries/nx729j` paths renamed to `Binaries/nx769j` |
| `Platforms/ZTE/nx769jPkg/Library/{MemoryMapLib,ConfigurationMapLib}/` | `nx729jPkg/Library/`'s, renamed — **see the warning below** |

## Not staged, and why

| File | Why it is not here |
| --- | --- |
| `Resources/DTBs/nx769j.dtb` | Extract from the device's `vendor_boot`; not collected. |
| `Binaries/nx769j/QcomPkg/Drivers/…` | Vendor UEFI DXE drivers, extracted from the device firmware package by `scripts/extract-files.py`. Not redistributable, so they cannot be staged here. |

`scripts/check-nx769j-firmware.py` reports exactly which of these are still
missing and whether they are fatal, and is what `./unixnu build firmware` runs
before EDK II. Against a fresh `UniXNU/uefi-sheng` checkout plus these files it
reports the tree as consistent with `board.toml`, with only the vendor drivers
absent.

## Warning: the memory map is not this board's

`MemoryMapLib.c` is nx729j's map with the identifiers renamed. Two of its
entries are known to be wrong for NX769J, because this board measures them
differently:

| Entry | nx729j's map | NX769J measured |
| --- | --- | --- |
| `HYP` | `0x80000000` / `0x00A00000` | `0x80000000` / `0x00E00000` (`gunyah_hyp_region`) |
| `Display Reserved` | `0xB8000000` / `0x02B00000` | `0xE3940000` / `0x02B00000` (`splash_region`, `cont_splash_region`) |

The rest of the table — XBL DT, AOP, SMEM, PIL, TZApps, HW Fence and the other
vendor reservations — is unverified. Those come from the device's own XBL, and
the only complete source is
`ls /proc/device-tree/reserved-memory/` with each node's `reg`, which
[`device-inputs.md`](../device-inputs.md) did not capture.

**Do not boot this firmware until the map is reconciled.** A memory map that
reserves the wrong ranges lets the firmware write over something the bootloader
or TrustZone owns. See the open items in
[`docs/UEFI-FIRMWARE.md`](../docs/UEFI-FIRMWARE.md).

## The one line that is easy to get wrong

`nx729j.dsc` includes `KailuaPkg/KailuaPkg.dsc.inc`. That is SM8550. NX769J is
SM8650, whose Mu-Silicium SoC package is **`LanaiPkg`** — named after Qualcomm's
platform codename, not the part number. The staged DSC includes `LanaiPkg` and
sets `SOC_TYPE = 2` (`SM8650-AB`).

The device agrees: its baseband is `LANAI_GEN_PACK` and its trustzone is
`LANAIAAAAANAZT`, and `LanaiPkg.dsc.inc` declares the GIC bases
`0x17100000` / `0x17180000` that this board measures.

## Provenance

Every value in these files, and the values still open, are in
[`docs/UEFI-FIRMWARE.md`](../docs/UEFI-FIRMWARE.md). The working reference is
`Platforms/ZTE/nx729jPkg` in
[`UniXNU/uefi-sheng`](https://github.com/UniXNU/uefi-sheng), branch `sheng`.
