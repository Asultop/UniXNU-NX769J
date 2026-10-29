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

Board values that no public NX769J source provides were read from a physical
device over read-only adb and recorded in
[`device-inputs.md`](device-inputs.md), with the command behind each value.

| Value | Status | Recorded in |
| --- | --- | --- |
| `userdata` first/last LBA, block size | **measured** 3302184 / 124002298 / 4096 | `board.toml` `[userdata]` |
| Splash reservation | **measured** `0xe3940000` / `0x2b00000`, `cont_splash_region` | `dts/nx769j.dts`, `board.toml` `[[bootimg.dtb_node]]` |
| Panel geometry | **measured** 1116x2480 | `porting.toml` display area |
| DRAM base and SKU | **measured** base `0x80000000`, 16 GiB unit | `dts/nx769j.dts` `memory` |
| OS window APFS volume UUID | **open** — exists only inside the installed iPadOS image | `board.toml` `payload.adt.root_match_volume_uuid` |

Re-run the commands in [`device-inputs.md`](device-inputs.md) before writing
anything to a device: the recorded GPT extents describe one unit at one point
in time, and a different SKU or a repartitioned device has different bounds.
[`scripts/collect-device-inputs.sh`](scripts/collect-device-inputs.sh) is the
same procedure in runnable form.

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

## Installing alongside Android

Writing the OS images into the `[userdata]` windows destroys Android's `/data`,
which is its user data partition. Android keeps its system images but no longer
boots to a usable state. To keep the stock system bootable, install into a
separate `unixnu` partition instead, using the
[dual-system partition](https://unixnu.com/porting/dual-system-partition) tool.

That tool shrinks the F2FS `userdata` filesystem and carves `unixnu` from the
end of the partition. It preserves `userdata`'s start, type, GUID and
attributes and leaves `metadata`, `super`, `boot` and every other partition
untouched. The whole procedure runs from userspace: host Python over ADB, with
the recovery shell doing the writes.

NX769J satisfies the layout requirements that can be checked offline:

| Requirement | NX769J |
| --- | --- |
| Filesystem F2FS, 4096-byte blocks | Logical sector size is 4096 (measured). `recovery.fstab` mounts `/data` as f2fs; confirm the live filesystem and F2FS section geometry with `partition.py inspect` |
| Compatible TWRP with root ADB | Several NX769J TWRP device trees exist |
| Kernel supports `F2FS_IOC_RESIZE_FS` | Stock kernel 6.1; validate the recovery kernel on the device |
| `userdata` is the last occupied partition, free GPT entry present | **Satisfied** — `userdata` is `sda12`, ends on the last usable sector, and 12 of 32 GPT entries are used (measured) |
| Encryption is direct userdata or one mapping backed only by userdata | **Unverified** — NX769J has a separate f2fs `metadata` partition; a stacked mapping makes the tool refuse |

### Verify the stock system still boots

Do this before writing any image. Back up `userdata` and `metadata` offline
first; the tool provides no automatic retry or rollback, and restoring the GPT
does not undo the F2FS relocation.

```sh
# 1. Back up, then inspect. Read-only; writes nothing to the device.
python3 scripts/dual_sys/partition.py inspect

# 2. Preview the split. Writes only host files and recovery /tmp.
python3 scripts/dual_sys/partition.py plan \
  --size-gib 32 --helper out/dual_sys/f2fs-shrink --output out/dual_sys/preview

# 3. Apply, then restart recovery and verify the new layout.
python3 scripts/dual_sys/partition.py apply \
  --size-gib 32 --helper out/dual_sys/f2fs-shrink --output out/dual_sys/applied
python3 scripts/dual_sys/partition.py verify --plan out/dual_sys/applied/plan.json

# 4. Prove the stock system still boots.
adb reboot system
```

Step 4 is the verification that matters: if Android reaches its lock screen,
the system partitions were never touched. If it does not, stop and have the
device maintainer assess the captured recovery state before anything else.

`unixnu` stays unformatted after the split and may still hold old `userdata`
bytes. Before writing an image, confirm the flash command targets `unixnu` and
not Android's `userdata`.

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
