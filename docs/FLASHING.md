# Package the image and flash it

How to turn this repository's build outputs into a bootable `boot.img` and start
it on the NX769J, following [UniXNU's boot procedure](https://unixnu.com/guide/boot).

Read this before touching the device. The first boot is started from RAM and
writes nothing; the step that does write is called out explicitly below.

## What has to exist first

| Input | State | Where it comes from |
| --- | --- | --- |
| XNU kernel | **built** | `./unixnu build kernel` produces `mach.development.bcm2837` |
| OS profile pins | **filled** | `os-profiles/ios-16.5-20F66/profile.toml`, extracted from the iOS 16.5 restore image |
| Board hardware values | **filled** | `device-inputs.md`, measured read-only on the device |
| `uefi-nx769j` firmware package | **missing** | Mu-Silicium platform package; see the firmware area of `porting.toml` |
| Firmware DTB | **missing** | extract from the device `vendor_boot` |
| `payload.text_fixups` | **missing** | derived from the dyld shared cache inside the OS image |
| `payload.adt.root_match_volume_uuid` | **missing** | the APFS volume UUID of the OS window once installed |

Only the firmware package, the firmware DTB and the two payload inputs are still
open. Everything else that the image assembly consumes is in place.

## 1. Build the parts

From the UniXNU checkout, in order, checking each output before continuing:

```sh
./unixnu defconfig nx769j_defconfig -D ../UniXNU-NX769J
./unixnu fetch -D ../UniXNU-NX769J
./unixnu build kernel   -D ../UniXNU-NX769J
./unixnu build package  -D ../UniXNU-NX769J
./unixnu build firmware -D ../UniXNU-NX769J --uefi ../uefi-nx769j
./unixnu build payload  -D ../UniXNU-NX769J
./unixnu build userdata -D ../UniXNU-NX769J    # only when the root image is being replaced
```

On Linux the kernel step uses the UniXNU open source Mach-O toolchain rather
than Xcode; `scripts/linux/setup-toolchain.py` installs it. `CCACHE` is free in
the XNU makefiles and `scripts/compile-records.py` uses it to record every
compile, which the component archive builders need.

Outputs land under `out/nx769j/ios-16.5-20F66/nx769j/`. This repository's
`package/` appears in the assembled tree as `kits/nx769j`.

## 2. Pack the boot image

```sh
./unixnu bootimg -D ../UniXNU-NX769J --uefi ../uefi-nx769j \
  --dtb <device tree> -o out/nx769j/ios-16.5-20F66/nx769j/boot/boot.img
```

`unixnu bootimg` round-trips the image and fails if any part does not match its
input, so a successful run is itself the check.

The image contains:

| Part | Contents |
| --- | --- |
| Kernel | gzip of BootShim followed by the UEFI firmware volume |
| Ramdisk | the UniXNU payload FAT volume: menu config, kernel, ADT, trust cache and Data seed |
| Appended data | the device tree the stock bootloader expects |

The stock Android bootloader loads the image, verifies the ARM64 header in
BootShim and jumps to the shim, which starts the firmware volume.

`board.toml` sets `header_version = 0`, `pagesize = 4096`, `base = 0x0`. The
value is 0 rather than the 4 that `BOARD_BOOTIMG_HEADER_VERSION` records,
because `unixnu bootimg`'s own verifier unpacks the header at the v0/v1/v2
offsets and a v4 header fails the round-trip check. If the NX769J ABL turns out
to reject a v0 image the answer is to extend that verifier, not to change the
value here.

## 3. Start it from RAM

```sh
fastboot devices
fastboot boot out/nx769j/ios-16.5-20F66/nx769j/boot/boot.img
```

`fastboot boot` transfers the image and starts it once. **It writes no
partition**, so it is repeatable, needs no backup, and a reset returns the
phone to its normal boot. This is the right first test.

It requires an **unlocked bootloader**. Unlocking is the one step that can wipe
`userdata`, and it is a one-time cost; if the device is already unlocked nothing
else is written.

Watch the boot in order:

| Stage | What to expect |
| --- | --- |
| UEFI | firmware starts, GOP framebuffer appears |
| UniXNU | version and configuration summary, then the menu |
| Payload | the FAT volume is read and the entry is selected |
| DarwinBoot | `DARWINBOOT:` lines, `boot_args` built, exit boot services |
| Kernel | `serial=3` kernel output |

Logs come from the serial console (`UNIXNU:` for the boot manager, `DARWINBOOT:`
for the loader, plain kernel output after handoff) and from
`out/nx769j/ios-16.5-20F66/nx769j/logs/*.log` on the host.

If it stalls before the menu, capture the last output, reset into the bootloader
and confirm `fastboot devices` still responds:

```sh
fastboot reboot bootloader
```

Then work through the failure isolation table in
[bring-up](https://unixnu.com/porting/bring-up).

## 4. Root storage, when you get that far

Stages 1 to 5 above need no root volume. Stage 6, mounting the OS window, does.
Two ways to provide it, and only one of them leaves Android usable:

**Keep Android: carve a `unixnu` partition.** Use the
[dual-system partition](https://unixnu.com/porting/dual-system-partition) tool.
It shrinks the F2FS `userdata` filesystem and takes the new partition from the
end, preserving `userdata`'s start, type, GUID and attributes and leaving
`metadata`, `super` and `boot` untouched.

```sh
python3 scripts/dual_sys/partition.py inspect
python3 scripts/dual_sys/partition.py plan  --size-gib 32 --helper out/dual_sys/f2fs-shrink --output out/dual_sys/preview
python3 scripts/dual_sys/partition.py apply --size-gib 32 --helper out/dual_sys/f2fs-shrink --output out/dual_sys/applied
python3 scripts/dual_sys/partition.py verify --plan out/dual_sys/applied/plan.json
adb reboot system          # the check: Android must still reach its lock screen
```

**Replace `userdata`.** This is the default UniXNU layout and it erases Android's
data partition:

```sh
fastboot flash userdata out/nx769j/ios-16.5-20F66/nx769j/userdata/userdata-root.img
fastboot reboot bootloader
```

Do not run that until `board.toml` `[userdata]` extents have been re-read from
the live GPT on the device in hand. They are recorded in `device-inputs.md` for
one unit and a different SKU or a repartitioned device has different bounds. A
wrong range overwrites an unrelated partition.

Before writing an image, confirm the flash command targets `unixnu` and not
Android's `userdata`.

## What this does not cover

Booting `boot.img` starts the kernel. Running the iOS userland additionally needs
the OS and SystemOS windows to exist with a root volume UUID that the kernel
matches. See `porting.toml` for what is still open on each step.
