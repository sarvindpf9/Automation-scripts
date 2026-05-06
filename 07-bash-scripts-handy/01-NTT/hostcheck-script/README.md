# hostcheck-script

Host health-check script for OpenStack KVM compute nodes. Validates storage, networking, and platform services required for stable hypervisor operation.

---

## `hostInfo-check.sh`

Runs a comprehensive set of read-only health checks on the local host — bond interfaces, NTP, packages, iSCSI, multipath, LVM, PF9 services, OVS bridges, and `/etc/hosts`. No IP input is required. Optionally adds a passwordless-sudo audit and a virsh VM disk/multipath inspection.

**Dependencies (local):**

- `ip`, `awk`, `timedatectl` — bond mode, NTP, and interface checks
- `dpkg` — package presence checks
- `systemctl` — service status (read-only)
- `iscsiadm` — iSCSI session listing (read-only, `iscsid` must be installed)
- `multipath` — `multipath -ll` listing (read-only)
- `ovs-vsctl` — OVS bridge enumeration (gracefully skipped if absent)
- `virsh` — VM UUID resolution and block device listing (only with `--uuid`)

**Dependencies (hypervisor / remote host):**

- Run directly on the target compute node as `root` or a privileged user
- No remote connections are made; all checks are local reads

**What it does:**

1. Parses optional `check-sudoers` and `--uuid` flags; errors on any unrecognised argument
2. Runs all host checks unconditionally (sections 2–12)
3. If `check-sudoers` is passed, also runs the passwordless sudo audit (section 1)
4. If `--uuid` is passed, also resolves the VM UUID and maps its block devices to multipath entries (section 13)

### Usage

```bash
# Run all host checks (no arguments required)
sudo ./hostInfo-check.sh

# Also run the passwordless sudo audit
sudo ./hostInfo-check.sh check-sudoers

# Also inspect a VM's disk/multipath mapping by UUID
sudo ./hostInfo-check.sh --uuid <vm-uuid>

# Write output to an auto-named timestamped log file
sudo ./hostInfo-check.sh --log

# Write output to a specific file
sudo ./hostInfo-check.sh --output /tmp/hostcheck.log

# All checks: host + sudoers + VM inspection + log file
sudo ./hostInfo-check.sh check-sudoers --uuid <vm-uuid> --log
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `check-sudoers` | No | Adds a passwordless sudo scan of `/etc/sudoers` and `/etc/sudoers.d/*` |
| `--uuid <vm-uuid>` | No | Adds virsh VM block device and multipath mapping check for the given UUID |
| `--log` | No | Writes output to `hostcheck-<hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory |
| `--output <file>` | No | Writes output to the specified file path |

> The terminal always receives coloured output. The log file receives the same output with ANSI colour codes stripped. A header line with hostname and timestamp is written at the top of the file.

### Checks performed

All sections below run on every invocation unless noted.

| # | Section | What it checks |
| - | ------- | -------------- |
| 1 | **Passwordless sudo** *(check-sudoers flag only)* | Scans `/etc/sudoers` and `/etc/sudoers.d/*` for users with `ALL=(ALL) NOPASSWD: ALL` |
| 2 | **Bond mode** | Detects all `type bond` interfaces; flags any not in `802.3ad` (LACP) mode; prints IP per bond |
| 3 | **NTP** | `timedatectl` — verifies NTP is active and system clock is synchronized |
| 4 | **Packages** | `dpkg -l` presence check for: `lsscsi`, `sg3-utils`, `multipath-tools`, `scsitools`, `open-iscsi`, `nfs-common` |
| 5 | **Services** | `systemctl is-active` for: `iscsid`, `multipathd` |
| 6 | **iSCSI initiator** | Reads `/etc/iscsi/initiatorname.iscsi`; lists active sessions via `iscsiadm -m session` |
| 7 | **iscsid.conf** | Validates six timeout parameters in `/etc/iscsi/iscsid.conf` against expected values; skipped silently if `iscsid` is not installed |
| 8 | **Multipath blacklist** | Parses `/etc/multipath.conf` — checks `defaults{}` (4 keys), `blacklist{}` entries, and the NETAPP `device{}` block (9 parameters); prints full file content at end of section |
| 9 | **LVM filters** | Checks `/etc/lvm/lvm.conf` for `filter` and `global_filter` stanzas |
| 10 | **PF9 services** | `systemctl` status for 13 PF9 services; if `pf9-ha-slave` is absent, additionally reports `pf9-remote-write` status; if `pf9-ostackhost` is running, checks `volume_use_multipath` and `iscsi_use_multipath` in `nova_override.conf`, prints the full file, then prints virsh/XML VM count and any UUID mismatches; if `pf9-cindervolume-base` is running, checks `reserved_percentage` and `goodness_function` in `cinder.conf` |
| 11 | **OVS bridges** | Lists all OVS bridges, their IPv4 addresses, and physical uplink ports (skips `patch`/`internal` types; lists all ports for `br-int`) |
| 12 | **`/etc/hosts`** | Prints a red advisory to review SVM FQDN/IP mappings, then prints full `/etc/hosts` contents |
| 13 | **Virsh VM** *(`--uuid` flag only)* | Resolves UUID to domain name; lists block devices via `virsh domblklist --details`; maps `dm-*` devices to `/dev/mapper/<name>` via `multipath -ll` |

### PF9 service config checks

These run automatically when the relevant service is detected as active — no flags required.

**`pf9-ostackhost` — `/opt/pf9/etc/nova/conf.d/nova_override.conf`**

| Parameter | Check |
| --------- | ----- |
| `volume_use_multipath` | Presence check — WARN if not set |
| `iscsi_use_multipath` | Presence check — WARN if not set |

Full file contents are printed after the parameter checks.

**`pf9-cindervolume-base` — `/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder.conf`**

| Parameter | Check |
| --------- | ----- |
| `reserved_percentage` | Presence check — WARN if not set |
| `goodness_function` | Presence check — WARN if not set |

---

### iscsid.conf expected values

| Parameter | Expected value |
| --------- | -------------- |
| `node.session.timeo.replacement_timeout` | `15` |
| `node.conn[0].timeo.login_timeout` | `5` |
| `node.conn[0].timeo.logout_timeout` | `5` |
| `node.session.err_timeo.abort_timeout` | `10` |
| `node.session.err_timeo.reset_timeout` | `15` |
| `node.session.err_timeo.lu_reset_timeout` | `20` |

### multipath.conf expected values

`defaults{}` block:

| Parameter | Expected value |
| --------- | -------------- |
| `find_multipaths` | `yes` |
| `no_path_retry` | `12` |
| `polling_interval` | `5` |
| `user_friendly_names` | `no` |

If netapp section is detected the recommended values are should be as below:

| Parameter | Expected value |
| --------- | -------------- |
| `path_grouping_policy` | `group_by_prio` |
| `prio` | `alua` |
| `failback` | `immediate` |
| `fast_io_fail_tmo` | `5` |
| `dev_loss_tmo` | `30` |
| `product` | `LUN.*` |
| `path_selector` | `service-time 0` |
| `features` | `0` |
| `hardware_handler` | `1 alua` |

### Output format

| Badge | Colour | Meaning |
| ----- | ------ | ------- |
| `[ OK ]` | green | Check passed |
| `[ FAIL ]` | red | Check failed or resource missing |
| `[ WARN ]` | yellow | Unexpected but non-fatal state |
| `[ NOTE ]` | red | Advisory requiring manual review |
| *(dim indent)* | dim | Informational detail line |

Sections are separated by a cyan bold header banner.

### Examples

```bash
# Run all host checks on the local node
sudo ./hostInfo-check.sh

# Run all checks + passwordless sudo audit
sudo ./hostInfo-check.sh check-sudoers

# Inspect VM disk/multipath mapping by UUID
sudo ./hostInfo-check.sh --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a

# Full run: all host checks + sudoers + VM inspection
sudo ./hostInfo-check.sh check-sudoers --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a
```

### Requirements

- **OS:** Debian/Ubuntu (uses `dpkg`, `systemctl`, `timedatectl`)
- **Privileges:** Requires `root` or a user with access to `virsh`, `multipath`, `iscsiadm`, and `ovs-vsctl`
- **Conditional tools:** `virsh` (only needed with `--uuid`); `ovs-vsctl` (OVS check skipped gracefully if absent); `iscsid` (section 7 skipped if not installed)
