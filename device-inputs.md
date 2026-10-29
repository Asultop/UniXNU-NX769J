# NX769J measured hardware inputs

Read-only measurements from a physical NX769J, taken to fill the board values
that no public source provides. Every command below is read-only: it prints
device state and writes nothing to the phone.

## Device identity

The connected handset reports a spoofed Xiaomi identity through its userspace
properties while the boot image, kernel and device tree identify NX769J. The
values recorded here come from the kernel, the device tree and the raw UFS
partition table, which userspace property spoofing does not affect.

| Field | Value | Source |
| --- | --- | --- |
| PCB version | `NX769J_V1A` | `getprop persist.sys.pcb_version_ext` |
| Boot image device | `NX769J` | `getprop ro.product.bootimage.device` |
| Marketing name | `nubia-9pro` (RedMagic 9 Pro) | `getprop ro.cc.device.name` |
| Firmware | `GEN_CN_NX769SV2.0.0B08` (RedMagic 9S build) | `getprop ro.build.sw_internal_version` |
| Boot image fingerprint | `nubia/NX769J/NX769J:14/UKQ1.230917.001/20250331.162825:user/release-keys` | `getprop ro.bootimage.build.fingerprint` |
| Kernel | `6.1.118-Huge-Dragon-AsulTop-0.0.3` | `uname -a` |
| Baseband | `SS.DE.5.0.c3-00030-LANAI_GEN_PACK-1.46586.104` | `getprop gsm.version.baseband` |

SoC identity from the device tree confirms the platform:

```
model          = Qualcomm Technologies, Inc. Pineapple MTP
compatible     = qcom,pineapple-mtp, qcom,pineapple, qcom,pineapplep-mtp,
                 qcom,pineapplep, qcom,mtp
qcom,msm-id    = 0x22d00020000, 0x24100020000     # msm_id 0x22d = SM8650
qcom,board-id  = 0x800000000
```

## Storage and partition geometry {#userdata}

```
adb shell 'sgdisk --print /dev/block/sda'
```

```
Disk /dev/block/sda: 124002304 sectors, 473.0 GiB
Sector size (logical/physical): 4096/4096 bytes
Partition table holds up to 32 entries
First usable sector is 6, last usable sector is 124002298

Number  Start (sector)    End (sector)    Size       Code  Name
   7         8968         3154695       12.0 GiB    FFFF  super
  10      3154728         3171111       64.0 MiB    FFFF  metadata
  12      3302184       124002298      460.4 GiB    A03A  userdata
```

`userdata` is `/dev/block/sda12`. These are the values `board.toml` records in
`[userdata]`:

| Key | Value |
| --- | --- |
| `first_lba` | `3302184` |
| `last_lba` | `124002298` |
| `lba_bytes` | `4096` |

`userdata` ends exactly on the last usable sector, so it is the last occupied
partition and no `unixnu` partition exists yet. The GPT table can hold 32
entries and uses 12. Both are preconditions of the
[dual-system partition](https://unixnu.com/porting/dual-system-partition) tool,
so a `unixnu` partition can be carved from the end of `userdata` without
touching any other entry.

`super` is 12.0 GiB. The `BOARD_SUPER_PARTITION_SIZE := 9126805504` in the
public NX769J board configurations is marked `TODO: Fix hardcoded value` there
and is not the real size.

## Reserved memory {#splash}

```
adb shell 'od -An -v -tx1 /proc/device-tree/reserved-memory/splash_region/reg'
```

| Property | Value |
| --- | --- |
| node name | `splash_region` |
| `label` | `cont_splash_region` |
| `reg` | `0xe3940000` size `0x2b00000` |

The node name and label match the convention UniXNU-sheng uses for
`/reserved-memory/splash_region`, and the region size `0x2b00000` is the same
as sheng and shennong. Only the address is board specific.

Other regions read from the same node, for the areas that will consume them:

| Region | Address / size |
| --- | --- |
| `gunyah_hyp_region` | `0x80000000` / `0xe00000` |
| `gpu_microcode_region` | `0x9b09a000` / `0x2000` |
| `non_secure_display_region` | size `0xa400000`, `alloc-ranges 0x0 0xffffffff` (allocated at runtime) |

**This is not the complete list.** The UEFI memory map needs every reservation,
and the four above are the ones read at the time. Re-run the `ls` and read each
node's `reg` before building the firmware map; see
[`firmware/README.md`](firmware/README.md).

### Cross-check against the public firmware dump {#dump}

The splash reservation is confirmed by a second, independent source: the DTBO
partition of [`Klozz/nubia_nx769j_dump`](https://github.com/Klozz/nubia_nx769j_dump),
a public dump of this device's firmware.

```
curl -L -o dtbo.dtb "https://raw.githubusercontent.com/Klozz/nubia_nx769j_dump/<branch>/dtbo/18_dtbdump_Qualcomm_Technologies,_Inc._Pineapple_QRD.dtb"
dtc -I dtb -O dts dtbo.dtb -o dtbo.dts
```

| Node | In the dump | Measured on the device |
| --- | --- | --- |
| `splash_region` `label = "cont_splash_region"` | `reg = <0x00 0xe3940000 0x00 0x2b00000>` | `0xe3940000` / `0x2b00000` |
| `disp_rdump_region` `label = "disp_rdump_region"` | `reg = <0xe3940000 0x800000>` | not read |
| `demura_region_0`, `demura_region_1` | `reg = <0 0 0 0>` (runtime) | not read |

The two agree exactly on the splash, which is the one reservation the boot image
has to advertise. `disp_rdump_region` is an eighth-megabyte display ramdump
window at the same base address, inside the splash region, and was not in the
measured set.

The same overlay declares `model = "Qualcomm Technologies, Inc. Pineapple QRD"`
with `compatible = "qcom,pineapple-qrd", "qcom,pineapple", "qcom,pineapplep-qrd",
"qcom,pineapplep", "qcom,qrd"`, which is where the base-board name in
`porting.toml` comes from.

The dump is an **overlay**, applied on top of a base DTB it does not contain: the
repository has `dtbo.img` and its extracted trees but no `vendor_boot` and no
base `dtb`. `gunyah_hyp_region`, `gpu_microcode_region` and the vendor
reservations live in that base, so the firmware DTB and the full memory map both
still need the device.

## DRAM

`gunyah_hyp_region@80000000` and the lowest System RAM range both place the
DRAM base at **0x80000000**, which is the ARM64 Qualcomm base and the value
already in `dts/nx769j.dts`.

```
MemTotal: 15705424 kB        # about 15.0 GiB usable, 16 GiB SKU
```

`/proc/iomem` and the kernel `memory` node report System RAM split into
separate ranges with reservations removed, including ranges above 4 GiB at
`0x880000000`, `0x8b0000000`, `0x8c0000000` and `0xa00000000`. UniXNU's device
tree takes one contiguous handoff window, not this multi-range map.

## SoC register map

`/proc/iomem` confirms the ranges that `dts/nx769j.dts` takes from the SoC
DTSI:

| Resource | Measured | In `dts/nx769j.dts` |
| --- | --- | --- |
| UFS PHY | `01d80000-01d81fff` | `0x01d80000 / 0x2000` |
| UFS host | `01d84000-01d86fff` | `0x01d84000 / 0x3000` |
| UFS inline crypto | `01d88000-01d8ffff` | not exported |

CPU MPIDR affinities from `/proc/device-tree/cpus/cpu@*/reg` are
`0x0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700`, matching the board DTS.

The vendor kernel names the cores `qcom,kryo`; the board DTS uses the mainline
ARM core names (`arm,cortex-a520`, `arm,cortex-a720`, `arm,cortex-x4`) that
mainline `sm8650.dtsi` declares and that the UniXNU CPU driver matches on.

## Display and input

```
card0-DSI-1: connected  modes=1116x2480x60cmd
```

Panel geometry is **1116x2480**, matching the value already recorded from the
public NX769J board configurations.

Input devices registered by the kernel:

| Device | Meaning |
| --- | --- |
| `goodix_ts` | Goodix touch controller, `goodix_ts/input0` |
| `goodix_fp` | Goodix fingerprint sensor |
| `gpio-keys_nubia` | nubia side buttons |
| `nubia_tgk_aw_sar0_ch0`, `nubia_tgk_aw_sar1_ch0` | Awinic SAR sensing |
| `pmic_pwrkey`, `pmic_resin` | PMIC power and reset keys |

`goodix_ts` confirms the touch controller family behind
`goodix_firmware_9916r.bin` in `proprietary-files.txt`.

## Storage topology

Eight SCSI devices are published: LUNs `0` through `4`, plus the UFS well-known
LUNs `49456` (RPMB), `49476` and `49488` (boot).

## Still not measured

| Value | Why | How to get it |
| --- | --- | --- |
| OS window APFS volume UUID | Lives inside the installed iPadOS image, not on the running Android system | Read it from the OS window's APFS volume once the image is installed, then set `payload.adt.root_match_volume_uuid` |

## Commands used

All read-only. `adb root` and any write, flash or reboot command was avoided.

```sh
adb devices -l
adb shell 'getprop ro.product.device; getprop ro.product.model; ...'
adb shell 'uname -a'
adb shell 'cat /proc/meminfo | head -4'
adb shell 'cat /proc/iomem'
adb shell 'ls /proc/device-tree/reserved-memory/'
adb shell 'od -An -v -tx1 /proc/device-tree/reserved-memory/splash_region/reg'
adb shell 'sgdisk --print /dev/block/sda'
adb shell 'blockdev --getss /dev/block/sda'
adb shell 'ls -l /dev/block/by-name/userdata'
adb shell 'for d in /sys/class/drm/*/; do ... done'
adb shell 'ls /sys/class/scsi_device/'
```
