# UniXNU-NX769J

UniXNU device repository for the **nubia RedMagic 9 series** — RedMagic 9 Pro,
9 Pro+, 9S Pro and 9S Pro+ — codename **NX769J**, on the Qualcomm **SM8650**
("pineapple", Snapdragon 8 Gen 3).

UniXNU boots iOS and macOS on non-Apple ARM64 hardware through UEFI. This
repository describes one board: its hardware values, component selection,
firmware and partition policy. Shared code lives in
[UniXNU](https://github.com/UniXNU/UniXNU) and in the component repositories.

| | |
| --- | --- |
| Board | nubia RedMagic 9 Pro / 9 Pro+ / 9S Pro / 9S Pro+ |
| Codename | `nx769j` (NX769J) |
| SoC | Qualcomm SM8650 "pineapple", Adreno 750 |
| Base board | Qualcomm Pineapple QRD (`qcom,pineapple-qrd`) |
| OS profile | `ipados-17.7.11-21H461` (XNU 10063.141.1) |
| Display | 1116x2480 at 480 dpi |
| Boot | UEFI, Android 14 ABL, boot header version 4, 4096-byte pages |
| Storage | UFS, A/B, userdata on f2fs |
| Touch | Goodix 9916R |
| Porting record | [`porting.toml`](porting.toml) |

## Status

The board description, component selection, device tree and kernel
configuration are complete and sourced. Hardware bring-up has not run: this
port has no firmware, no device verification and no host verification yet.
Every area states its own scope and next step in [`porting.toml`](porting.toml).

Four values cannot be sourced from any public NX769J reference and are left
open on purpose. They are safety critical or identity critical, so they are
never guessed:

| Value | Goes in | Why it is open |
| --- | --- | --- |
| `userdata` first/last LBA, block size | `board.toml` `[userdata]` | A wrong range overwrites an unrelated partition |
| Splash reservation | `dts/nx769j.dts`, `board.toml` `[[bootimg.dtb_node]]` | Board specific, taken from the firmware memory map |
| OS window APFS volume UUID | `board.toml` `payload.adt.root_match_volume_uuid` | Read from the installed OS image |
| DRAM size per SKU | `dts/nx769j.dts` `memory` | 8 to 24 GiB depending on SKU |

Run [`scripts/collect-device-inputs.sh`](scripts/collect-device-inputs.sh) on the
device to produce all four.

## Prerequisites

Host tools from [Requirements](https://unixnu.com/guide/requirements), plus a
checkout of [UniXNU](https://github.com/UniXNU/UniXNU) and of
[UniXNU-sm8550-common](https://github.com/UniXNU/UniXNU-sm8550-common) as the
SoC source. There is no `UniXNU-sm8650-common`; see
[`porting.toml`](porting.toml) for why the SM8550 repository is used and what it
does not cover.

## Build

From the UniXNU checkout:

```sh
./unixnu defconfig nx769j_defconfig -D ../UniXNU-NX769J
./unixnu fetch -D ../UniXNU-NX769J
./unixnu status --json -D ../UniXNU-NX769J
./unixnu tree -D ../UniXNU-NX769J
python3 scripts/porting-record.py check --device ../UniXNU-NX769J
```

Then follow [Building](https://unixnu.com/building) in order: kernel, package,
firmware, payload, userdata when required, then boot image. Output lands in
`out/nx769j/ipados-17.7.11-21H461/<config>/` and this repository's `package/`
appears there as `kits/nx769j`.

Copy `local.toml.example` to the ignored `local.toml` for machine-specific
source overrides.

## Component selection

`board.toml` lists the complete selection, because arrays replace the inherited
ARM64, SoC and OS arrays.

Selected: `ArmDTPlatform`, `ArmCpu`, `SoftwareAES`, `XnuPrelink`, `DarwinBoot`,
`ShengUfs`, `VirtioMmioBlock`, `VerifiedRoot`, `GopFramebuffer`.

Not selected, and why:

| Component | Reason |
| --- | --- |
| `Adreno740`, `AdrenoMetal`, `Sm8550Platform`, `AdrenoPM4`, `AdrenoFirmware`, `ArmSmmu4K` | Targets Adreno 740 on SM8550. This board has Adreno 750 (`qcom,adreno-43051401`, `qcom,adreno-gmu-750.1`) with no qualified driver |
| `ShengHidInput`, `ShengNovatekTouch`, `QcomGeniSpi` | Written for the Novatek NT36532E. This board has a Goodix 9916R |
| `Ath12kWifi` | Declares `os_abi` `nw_abi platform interface`, which does not match `ipados-17.7.11-21H461` |

## Documentation

| Topic | Documentation |
| --- | --- |
| Porting | [Porting](https://unixnu.com/porting/), [steps](https://unixnu.com/porting/steps), [device repository](https://unixnu.com/porting/device-repository) |
| Hardware | [Device tree](https://unixnu.com/porting/device-tree), [SoC support](https://unixnu.com/porting/soc-support) |
| Drivers | [Adaptation order](https://unixnu.com/porting/drivers), [component catalog](https://unixnu.com/reference/components) |
| Images | [Prelink](https://unixnu.com/concepts/prelink), [payload](https://unixnu.com/concepts/payload), [boot chain](https://unixnu.com/concepts/boot-chain) |
| Verification | [Building](https://unixnu.com/building), [bring-up](https://unixnu.com/porting/bring-up), [log capture](https://unixnu.com/porting/log-capture) |
| Record | [Porting records](https://unixnu.com/porting/records), [`porting.toml`](porting.toml) |
