# mpath-iscsi-disk-cleanup.sh

Inspects multipath devices on a KVM/libvirt host, identifies orphaned mpath maps not claimed by any VM, checks whether the host itself is consuming them, and optionally removes confirmed orphans along with their underlying SCSI paths.

---

## `mpath-disk-cleanup.sh`

Parses `multipath -ll` and cross-references every device against VM XML definitions in `/etc/libvirt/qemu/`. For each device absent from all VM configs, it runs five host-consumer checks before flagging it as safe for cleanup. Optionally writes flat output files listing orphaned WWIDs and `sd*` paths for use in downstream workflows, and can flush mpath maps and remove SCSI paths in a single pass.

**Dependencies (local):**

- `multipath` — parses `multipath -ll`; required for all commands
- `dmsetup` — validates sysfs holder liveness before treating an entry as an active consumer
- `virsh` — lists running VMs and queries per-VM block device details (required for `vm-mpath`)
- `pvs` — detects LVM physical volumes on a device; skipped gracefully if absent
- `lsof` — detects open file descriptors; `fuser` is used as fallback if absent
- `awk`, `grep`, `sed` — standard text processing
- Root or `sudo` — required for `multipath`, `pvs`, sysfs reads, and cleanup writes

**Dependencies (hypervisor / remote host):**

- `/etc/libvirt/qemu/*.xml` — VM definition files used to build the `dm-X → domain` reference map
- `/proc/mounts`, `/proc/mdstat` — kernel pseudo-files read during host consumer checks
- `/sys/block/<dm>/holders/` — sysfs hierarchy queried for stacked device detection
- `/sys/block/<sd>/device/delete` — sysfs write path used by `cleanup` to remove SCSI paths

**What it does:**

1. Runs `multipath -ll` and parses each stanza into an in-memory `dm-X → alias/WWID` map.
2. Reads all XML files under `/etc/libvirt/qemu/` to build a `dm-X → domain` reference map.
3. (`orphans`) For each mpath device not referenced by any VM XML, runs five host consumer checks and prints findings. Only devices with no live consumers are queued for output files and cleanup.
4. (`vm-mpath`) Queries `virsh domblklist` for each running VM and reports active/degraded/dead path counts per attached device.
5. (`orphans`) Writes three output files to `OUTPUT_DIR`: a WWID list, an `sd*` device list, and a WWID ↔ `sd*` association file.
6. (`cleanup`) For each queued orphan: flushes the multipath map with `multipath -f`, then removes each underlying SCSI path via `echo 1 > /sys/block/<sd>/device/delete`. Dry-run by default.

### Usage

```bash
# Report orphaned mpath devices with host consumer details
sudo bash mpath-disk-cleanup.sh orphans

# Report per-VM multipath path state for all running VMs
sudo bash mpath-disk-cleanup.sh vm-mpath

# Run both reports in one pass
sudo bash mpath-disk-cleanup.sh orphans vm-mpath

# Report orphans and write output files to a specific directory
sudo bash mpath-disk-cleanup.sh orphans --output-dir /tmp/mpath-cleanup

# Dry-run cleanup — shows what would be removed, touches nothing
sudo bash mpath-disk-cleanup.sh orphans cleanup

# Live cleanup — flushes orphaned maps and removes underlying SCSI paths
sudo bash mpath-disk-cleanup.sh orphans cleanup --execute
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `orphans` | At least one command required | Reports mpath devices not referenced by any VM XML and runs host consumer checks on each |
| `vm-mpath` | At least one command required | Reports active/degraded/dead path counts per disk for all running VMs |
| `cleanup` | No | Flushes orphaned maps and removes underlying SCSI paths; must be combined with `orphans` in the same invocation |
| `--output-dir <dir>` | No | Directory for output files (default: current directory) |
| `--execute` | No | Arms live removal for `cleanup`; omitting this flag runs cleanup in dry-run mode |
| `-h`, `--help` | No | Prints usage and exits |

### Output files

All files are written to `OUTPUT_DIR` (default: current directory) and share the same `<host>-<timestamp>` suffix.

| File | Written when | Content |
| ---- | ------------ | ------- |
| `mpath-ids-orphans-<host>-<timestamp>.txt` | `orphans` + at least one unconsumed orphan found | One WWID per line |
| `mpath-sd-devices-orphans-<host>-<timestamp>.txt` | `orphans` + at least one unconsumed orphan found | One `sd*` device per line |
| `mpath-assoc-orphans-<host>-<timestamp>.txt` | `orphans` + at least one unconsumed orphan found | WWID followed by its `sd*` paths on each line |
| `mpath-cleanup-<dryrun\|execute>-<host>-<timestamp>.log` | `cleanup` | Timestamped plain-text log of the full cleanup section output (dry-run or live) |

### Host consumer checks

Run for every device not referenced by any VM XML. A device is only queued for output files and cleanup if all five checks find no consumers.

| Check | What is inspected |
| ----- | ----------------- |
| Mounted filesystem | `/proc/mounts` — device or mapper path matched as mount source |
| Sysfs holder | `/sys/block/<dm>/holders/` — each listed holder verified live via `dmsetup info`; stale sysfs entries (device gone from DM but directory not cleaned up) are reported as ignored rather than counted as consumers |
| LVM physical volume | `pvs /dev/<dm>` — if a PV exists, the VG name is reported; flagged as orphan PV if no VG is assigned |
| MD RAID member | `/proc/mdstat` — device name matched against active array members |
| Open file descriptors | `lsof /dev/<dm>` (up to 5 processes shown); `fuser` used as fallback if `lsof` is not installed |

### Cleanup behaviour

`cleanup` requires `orphans` in the same invocation. It operates only on the devices that passed all host consumer checks in the orphan scan.

For each device the removal sequence is:

1. `multipath -f <map>` — flushes the DM map from the kernel. If this step fails, `sd*` path removal is skipped for that device and it is counted as a failure.
2. `echo 1 > /sys/block/<sd>/device/delete` — issued for each underlying SCSI path device.

Dry-run mode (default) prints every command that would run without executing any of them. Pass `--execute` to arm live removal.

A timestamped log of the cleanup section output is always written to `OUTPUT_DIR` as `mpath-cleanup-<dryrun|execute>-<host>-<timestamp>.log`. The path is printed as the last line of cleanup output.

#### Example dry-run output

```
━━━  MULTIPATH CLEANUP          ━━━
  [ WARN ]  Dry run — pass --execute to perform actual removal

             Target: 3600a098038314e65782b575176676c6a (dm-40) — paths: sdaf sdaq
             [DRY RUN] multipath -f 3600a098038314e65782b575176676c6a
             [DRY RUN] echo 1 > /sys/block/sdaf/device/delete
             [DRY RUN] echo 1 > /sys/block/sdaq/device/delete

             Dry run: 1 device(s) would be processed — rerun with --execute to apply
```

#### Example orphan output with stale sysfs holders

```
  [ WARN ]  Orphan: 3600a098038314e65782b575176676c6a (dm-40) — not referenced by any VM XML
               3600a098038314e65782b575176676c6a dm-40 NETAPP,LUN C-Mode
               size=531G features='1 queue_if_no_path' hwhandler='1 alua' wp=rw
               |-+- policy='service-time 0' prio=50 status=active
               | `- 18:0:0:38 sdaq 66:160 active ready running
               `-+- policy='service-time 0' prio=10 status=enabled
                 `- 17:0:0:38 sdaf 65:240 active ready running
               [HOST] stale sysfs holder (device gone): dm-63 — ignored
               [HOST] stale sysfs holder (device gone): dm-64 — ignored
               [HOST] stale sysfs holder (device gone): dm-65 — ignored
               no host consumers — queued for cleanup
```

#### Example orphan output with active host consumer

```
  [ WARN ]  Orphan: 3600a098038314e65782b575176676e56 (dm-41) — not referenced by any VM XML
               ...
               [HOST] sysfs holder: dm-66
               skipped: device has active host consumers (see above)
```
