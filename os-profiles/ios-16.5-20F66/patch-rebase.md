# Rebase status: UniXNU XNU patches onto xnu-8796

The resolved patch order for this port targets `xnu-10063.141.1`. This file
records how each patch fares against the iOS 16.5 baseline,
`xnu-8796.101.5` (`aca3beaa3dfbd42498b42c5e5ce20a938e6554e5`), measured with
`git apply --check` on a clean checkout.

## Result

| Status | Count | Meaning |
| --- | --- | --- |
| clean | 46 | applies unchanged |
| fuzz `-C1` | 1 | context drifted by one line; applies with reduced context |
| manual | 11 | context drifted past fuzz; needs the hunk re-anchored |
| structural | 1 | target path does not exist in this train |

So 47 of 59 carry over without editing and 12 need work. The failures cluster
into a few files rather than being spread out:

| Cluster | Patches | Note |
| --- | --- | --- |
| `bsd/kern/kern_exec.c` | 4 | `offline-owner-systemos-mount`, `zzy-native-gpu-addon-mount`, `zzy-staged-system-apps`, `zzyb-native-cryptex-os-view` |
| `osfmk/arm64/start.s` + `config/MASTER` | 2 | `apple-only-cpu-tunables`, `source-machine-layer` |
| one file each | 5 | `makedefs/MakeInc.kernel`, `iokit/KernelConfigTables.cpp`, `osfmk/kern/zalloc.c`, `EXTERNAL_HEADERS/CoreEntitlements/CoreEntitlements.h`, `bsd/kern/kern_memorystatus_freeze.c` |
| SPTM pmap layout | 1 | `zzx-pmap-sync-64bit-pa` |

`zzx-pmap-sync-64bit-pa.patch` is the only structural case: it touches
`osfmk/arm64/sptm/pmap/pmap.c`, and `osfmk/arm64/sptm/` does not exist in
8796. Its `osfmk/arm/pmap/pmap.c` half targets a path that does exist, so the
change has to be ported to the 8796 pmap layout rather than dropped.

`native-text-fixup.patch` is among the 46 that apply cleanly, which means
`payload.text_fixups` becomes relevant as soon as the rebase lands.

## Reproduce

```sh
git clone https://github.com/apple-oss-distributions/xnu.git xnu
git -C xnu checkout aca3beaa3dfbd42498b42c5e5ce20a938e6554e5
for p in UniXNU/patches/xnu/*.patch; do
  git -C xnu apply --check "$p" && echo "clean  $p" || echo "manual $p"
done
```

Pass absolute patch paths: `git -C` changes directory first, so a relative
patch name is looked up inside the source tree.

## Per patch

| `apple-only-cpu-tunables.patch` | manual | `osfmk/arm64/start.s` |
| `architectural-timer-entry.patch` | clean | `osfmk/arm64/start.s` |
| `armvirt-platform-personality.patch` | clean | `iokit/KernelConfigTables.cpp` |
| `cxx-flag-dependencies.patch` | clean | `bsd/conf/Makefile.template` |
| `disabled-deferred-reclaim.patch` | clean | `osfmk/vm/vm_user.c` |
| `external-archive-dependencies.patch` | manual | `makedefs/MakeInc.kernel` |
| `kernel-sdk-root.patch` | clean | `makedefs/MakeInc.def` |
| `local-availability.patch` | clean | `bsd/sys/make_symbol_aliasing.sh` |
| `mockfs-intermediate-lookup.patch` | clean | `bsd/miscfs/mockfs/mockfs_vnops.c` |
| `mockfs-memory-device-width.patch` | clean | `bsd/miscfs/mockfs/mockfs_vfsops.c` |
| `mockfs-statfs.patch` | clean | `bsd/miscfs/mockfs/mockfs_vfsops.c` |
| `mockfs-test-file.patch` | clean | `bsd/miscfs/mockfs/mockfs_fsnode.h` |
| `mockfs-typed-allocation.patch` | clean | `bsd/miscfs/mockfs/mockfs_fsnode.c` |
| `native-4k-bootstrap-capacity.patch` | clean | `osfmk/arm/pmap/pmap.h` |
| `native-4k-signature-hash-cache.patch` | clean | `bsd/sys/ubc_internal.h` |
| `native-4k-user-abi.patch` | clean | `bsd/kern/mach_loader.c` |
| `native-aes-personality.patch` | fuzz -C1 | `iokit/KernelConfigTables.cpp` |
| `native-arm-pan.patch` | clean | `pexpert/pexpert/arm64/BCM2837.h` |
| `native-dt-panic-region.patch` | clean | `pexpert/arm/pe_init.c` |
| `native-lookup-trace.patch` | clean | `bsd/vfs/vfs_lookup.c` |
| `native-priv-work-interval.patch` | clean | `bsd/kern/kern_priv.c` |
| `native-quiet-managed-page-report.patch` | clean | `iokit/Kernel/IOMemoryDescriptor.cpp` |
| `native-smp-secondary.patch` | clean | `pexpert/pexpert/arm64/board_config.h` |
| `native-text-fixup.patch` | clean | `bsd/kern/ubc_subr.c` |
| `native-trust-cache-runtime.patch` | clean | `osfmk/kern/startup.c` |
| `native-union-getattrlistbulk.patch` | clean | `bsd/vfs/vfs_attrlist.c` |
| `native-union-lower-directory.patch` | clean | `bsd/vfs/vfs_lookup.c` |
| `native-work-interval-instance.patch` | clean | `bsd/kern/sys_work_interval.c` |
| `native-work-interval-soft-fail.patch` | clean | `osfmk/kern/work_interval.c` |
| `native-work-interval-trace.patch` | clean | `bsd/kern/sys_work_interval.c` |
| `non-apple-cache-monitor.patch` | clean | `osfmk/arm64/arm_vm_init.c` |
| `non-apple-iommu-bootstrap.patch` | clean | `osfmk/arm/pmap/pmap.c` |
| `non-apple-pmap-field.patch` | clean | `osfmk/arm/pmap/pmap.h` |
| `null-root-media.patch` | clean | `iokit/Kernel/IOService.cpp` |
| `offline-component-load-probes.patch` | clean | `bsd/kern/bsd_init.c` |
| `offline-legacy-start.patch` | clean | `bsd/kern/bsd_init.c` |
| `offline-native-gpu-broker.patch` | clean | `bsd/kern/bsd_init.c` |
| `offline-owner-boot-manifest.patch` | clean | `iokit/bsddev/IOKitBSDInit.cpp` |
| `offline-owner-cache-carrier.patch` | clean | `bsd/vm/vm_unix.c` |
| `offline-owner-root-binding-audit.patch` | clean | `bsd/kern/bsd_init.c` |
| `offline-owner-root-crypto-probe.patch` | clean | `bsd/kern/bsd_init.c` |
| `offline-owner-systemos-mount.patch` | manual | `bsd/kern/kern_exec.c` |
| `offline-owner-z-air-init.patch` | clean | `bsd/kern/kern_exec.c` |
| `offline-pgz-alignment-probe.patch` | clean | `osfmk/kern/zalloc.c` |
| `pgz-aligned-validation.patch` | manual | `osfmk/kern/zalloc.c` |
| `public-entitlements-header.patch` | manual | `EXTERNAL_HEADERS/CoreEntitlements/CoreEntitlements.h` |
| `published-freezer-condition.patch` | manual | `bsd/kern/kern_memorystatus_freeze.c` |
| `sheng-platform-power.patch` | clean | `bsd/kern/bsd_init.c` |
| `source-corecrypto14-bootstrap.patch` | clean | `osfmk/prng/prng_random.c` |
| `source-machine-layer.patch` | manual | `config/MASTER` |
| `source-pthread-bootstrap.patch` | clean | `` |
| `zzw-native-adreno-sandbox-grant.patch` | clean | `iokit/Kernel/IOUserClient.cpp` |
| `zzwb-native-sandbox-grant-set-properties.patch` | clean | `iokit/Kernel/IOUserClient.cpp` |
| `zzx-pmap-sync-64bit-pa.patch` | structural | `osfmk/arm/pmap/pmap.c` |
| `zzy-native-gpu-addon-mount.patch` | manual | `bsd/kern/kern_exec.c` |
| `zzy-staged-system-apps.patch` | manual | `bsd/kern/kern_exec.c` |
| `zzyb-native-cryptex-os-view.patch` | manual | `bsd/kern/kern_exec.c` |
| `zzyc-owner-skip-launch-constraints.patch` | clean | `security/mac_process.c` |
| `zzz-boot-progress.patch` | manual | `osfmk/arm/arm_init.c` |
