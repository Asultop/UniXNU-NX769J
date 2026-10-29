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

`firmware/` is laid out as it lands in the checkout:

| Staged path | In the checkout | Origin |
| --- | --- | --- |
| `Resources/Configs/nx769j.toml` | same | derived from `nx729j.toml`, `header_version` 4 |
| `Platforms/ZTE/nx769jPkg/nx769j.dsc` | same | derived from `nx729jPkg/nx729j.dsc` |
| `Platforms/ZTE/nx769jPkg/nx769j.fdf` | same | derived from `nx729jPkg/nx729j.fdf` |

## Not staged, and why

| File | Why it is not here |
| --- | --- |
| `Platforms/ZTE/nx769jPkg/Include/{APRIORI,DXE,RAW}.inc` | Copy from `nx729jPkg/Include/` and rename the `Binaries/nx729j` paths to `Binaries/nx769j`. They are long vendor INF lists whose only board-specific content is the binary directory. |
| `Platforms/ZTE/nx769jPkg/{nx769j.dec,DeviceBuild.py}` | Copy from `nx729jPkg/` and rename. |
| `Platforms/ZTE/nx769jPkg/Library/{MemoryMapLib,ConfigurationMapLib}/` | Not written yet. `MemoryMapLib.c` is the board memory map and must agree with the measured reservations in [`docs/UEFI-FIRMWARE.md`](../docs/UEFI-FIRMWARE.md). `ConfigurationMapLib.c` is shared with every Lanai board and follows `nx729jPkg`'s. |
| `Resources/DTBs/nx769j.dtb` | Extract from the device's `vendor_boot`; not collected. |
| `Binaries/nx769j/QcomPkg/Drivers/…` | Vendor UEFI DXE drivers, extracted from the device firmware package by `scripts/extract-files.py`. Not redistributable, so they cannot be staged here. |

`scripts/check-nx769j-firmware.py` reports exactly which of these are still
missing and whether they are fatal, and is what `./unixnu build firmware` runs
before EDK II.

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
