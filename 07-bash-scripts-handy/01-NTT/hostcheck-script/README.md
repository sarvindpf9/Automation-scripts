# hostcheck-script

Host health-check script for OpenStack KVM compute nodes. Validates storage, networking, and platform services required for stable hypervisor operation.

---

## `hostInfo-check.sh`

Runs a comprehensive set of read-only health checks on the local host — bond interfaces, NTP, packages, iSCSI, multipath, LVM, PF9 packages, PF9 services, OVS bridges, and `/etc/hosts`. No IP input is required. Optionally adds a passwordless-sudo audit and a virsh VM disk/multipath inspection.

**Dependencies (local):**

- `ip`, `awk`, `timedatectl` — bond mode, NTP, and interface checks
- `dpkg` — package presence checks
- `systemctl` — service status (read-only)
- `iscsiadm` — iSCSI session listing (read-only, `iscsid` must be installed)
- `multipath` — `multipath -ll` listing (read-only)
- `ovs-vsctl` — OVS bridge enumeration (gracefully skipped if absent)
- `virsh` — VM liveness check (section 15, unconditional); per-VM disk/path listing (section 14, `list-vm-mpath`); UUID resolution and block device mapping (section 16, `--uuid`); gracefully skipped for sections 14 and 15 if absent

**Dependencies (hypervisor / remote host):**

- Run directly on the target compute node as `root` or a privileged user
- No remote connections are made; all checks are local reads

**What it does:**

1. Parses optional flags; errors on any unrecognised argument
2. Runs all host checks and virsh liveness unconditionally (sections 2–12 and 15; note the script labels both OVS bridges and /etc/hosts as section 12)
3. If `check-sudoers` is passed, also runs the passwordless sudo audit (section 1)
4. If `check-mpath-orphan` is passed, scans for orphaned or faulty multipath devices (section 13)
5. If `list-vm-mpath` is passed, lists per-VM DM disks and multipath path state (section 14)
6. If `--uuid` is passed, also resolves the VM UUID and maps its block devices to multipath entries (section 16)

### Usage

```bash
# Run all host checks (no arguments required)
sudo ./hostInfo-check.sh

# Also run the passwordless sudo audit
sudo ./hostInfo-check.sh check-sudoers

# Also inspect a VM's disk/multipath mapping by UUID
sudo ./hostInfo-check.sh --uuid <vm-uuid>

# Check for orphaned or faulty multipath devices
sudo ./hostInfo-check.sh check-mpath-orphan

# List per-VM DM disks and multipath path state
sudo ./hostInfo-check.sh list-vm-mpath

# Write output to an auto-named timestamped log file
sudo ./hostInfo-check.sh --log

# Write output to a specific file
sudo ./hostInfo-check.sh --output /tmp/hostcheck.log

# All checks: host + sudoers + orphans + VM mpath + VM inspection + log file
sudo ./hostInfo-check.sh check-sudoers check-mpath-orphan list-vm-mpath --uuid <vm-uuid> --log
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `check-sudoers` | No | Adds a passwordless sudo scan of `/etc/sudoers` and `/etc/sudoers.d/*` |
| `check-mpath-orphan` | No | Checks for multipath devices not referenced by any VM XML, and flags any device with failed/faulty paths |
| `list-vm-mpath` | No | For each running VM, prints its DM-* disks, the corresponding multipath map name, and path state (active/degraded/dead) |
| `--uuid <vm-uuid>` | No | Adds virsh VM block device and multipath mapping check for the given UUID |
| `--log` | No | Writes output to `hostcheck-<hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory |
| `--output <file>` | No | Writes output to the specified file path |
| `--virsh` | No | Accepted for backwards compatibility; has no effect (`--uuid` implies virsh) |

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
| 7 | **iscsid.conf** | Validates five timeout parameters in `/etc/iscsi/iscsid.conf` against expected values; skipped silently if `iscsid` is not installed |
| 8 | **Multipath blacklist** | Parses `/etc/multipath.conf` — checks `defaults{}` (4 keys), `blacklist{}` entries, and the NETAPP `device{}` block (9 parameters); prints full file content at end of section |
| 9 | **LVM filters** | Checks `/etc/lvm/lvm.conf` for `filter` and `global_filter` stanzas |
| 10 | **PF9 packages** | `dpkg -l` presence check for 16 PF9/OVN packages: `openvswitch-common`, `openvswitch-switch`, `ovn-common`, `ovn-host`, `pf9-cindervolume-base`, `pf9-cindervolume-config`, `pf9-comms`, `pf9-glance-role`, `pf9-ha-slave`, `pf9-hostagent`, `pf9-ip-discovery`, `pf9-neutron-base`, `pf9-neutron-ovn-controller`, `pf9-neutron-ovn-metadata-agent`, `pf9-ostackhost`, `python3-openvswitch` |
| 11 | **PF9 services** | `systemctl` status for 13 PF9 services; if `pf9-ha-slave` is absent, additionally reports `pf9-remote-write` status; if `pf9-ostackhost` is running, checks `volume_use_multipath` and `iscsi_use_multipath` in `nova_override.conf`, prints the full file, then prints virsh/XML VM count and any UUID mismatches; if `pf9-cindervolume-base` is running, checks `reserved_percentage` and `goodness_function` in `cinder.conf` |
| 12 | **OVS bridges** | Lists all OVS bridges, their IPv4 addresses, and physical uplink ports (skips `patch`/`internal` types; lists all ports for `br-int`) |
| 12 | **`/etc/hosts`** *(also labeled 12 in script)* | Prints a red advisory to review SVM FQDN/IP mappings, then prints full `/etc/hosts` contents |
| 13 | **Multipath orphans** *(check-mpath-orphan flag only)* | Builds a map of all `dm-*` devices referenced by VM XMLs in `/etc/libvirt/qemu/`; any multipath device not in that map is flagged as an orphan (leftover from a deleted/detached VM); additionally scans every device stanza for `failed`/`faulty` path lines and reports `[ FAIL ]` regardless of VM association |
| 14 | **VM disk multipath** *(list-vm-mpath flag only)* | For each running VM, retrieves its UUID and DM-* block devices (via `virsh domblklist`, with XML fallback); pre-parses `multipath -ll` once into per-`dm-X` maps and classifies each device as `active` (all paths up), `degraded` (some paths up), or `dead` (no active paths) |
| 15 | **Virsh liveness** | Runs `virsh list --all` with a 10 s timeout; on timeout or error, scans for defunct/zombie qemu processes, resolves their VM UUID via cmdline or `/var/run/libvirt/qemu/*.pid` files, then prints the full `multipath -ll` stanza for each DM disk belonging to the zombie VM |
| 16 | **Virsh VM** *(`--uuid` flag only)* | Resolves UUID to domain name; lists block devices via `virsh domblklist --details`; maps `dm-*` devices to `/dev/mapper/<name>` via `multipath -ll` |

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
./hostcheck-v5.sh

━━━  2.  CHECK BOND MODE ━━━
  [ OK ]  bond0  mode: IEEE 802.3ad Dynamic link aggregation  IP: none
  [ OK ]  bond1  mode: IEEE 802.3ad Dynamic link aggregation  IP: none

━━━  3.  NTP   ━━━
  [ OK ]  NTP active and clock synchronized

━━━  4.  PACKAGES ━━━
  [ OK ]  lsscsi
  [ OK ]  sg3-utils
  [ OK ]  multipath-tools
  [ OK ]  scsitools
  [ OK ]  open-iscsi
  [ OK ]  nfs-common

━━━  5.  SERVICES ━━━
  [ OK ]  iscsid is running
  [ OK ]  multipathd is running

━━━  6.  ISCSI INITIATOR ━━━
  [ OK ]  iqn.2004-10.com.ubuntu:01:dfbae5d5032-xxx
  [ OK ]  iscsid: running
             iSCSI sessions:
               tcp: [1] xxx.xxx.xx.xx:3260,1029 iqn.1992-08.com.netapp:sn.1387eeed321711ef833dd039eab7da2d:vs.8 (non-flash)
               tcp: [2] xxx.xxx.xxx.xxx:3260,1028 iqn.1992-08.com.netapp:sn.1387eeed321711ef833dd039eab7da2d:vs.8 (non-flash)

━━━  7.  ISCSID CONF ━━━
  [ WARN ]  node.session.timeo.replacement_timeout = 120  (expected: 15)
  [ WARN ]  node.conn[0].timeo.login_timeout = 15  (expected: 5)
  [ WARN ]  node.conn[0].timeo.logout_timeout = 15  (expected: 5)
  [ WARN ]  node.session.err_timeo.abort_timeout = 15  (expected: 10)
  [ WARN ]  node.session.err_timeo.lu_reset_timeout = 30  (expected: 20)

━━━  8.  MULTIPATH BLACKLIST ━━━
  [ OK ]  defaults: find_multipaths = yes
  [ FAIL ]  defaults: no_path_retry missing  (expected: 12)
  [ FAIL ]  defaults: polling_interval missing  (expected: 5)
  [ OK ]  defaults: user_friendly_names = no
  [ OK ]  blacklist: entries found:
               wwid nvme-eui.xxx
               wwid nvme-eui.xxx
  [ WARN ]  devices: no NETAPP device block found.

             ── /etc/multipath.conf ──
             defaults {
             user_friendly_names no
             find_multipaths yes
             }
             blacklist {
             wwid nvme-eui.xxx
             wwid nvme-eui.xxx
             }

━━━  9.  LVM FILTERS ━━━
  [ OK ]  filter:                  filter = [ "a|^/dev/nvme[0-9]+n[0-9]+$|", "a|^/dev/nvme[0-9]+n[0-9]+p[0-9]+$|", "a|^/dev/md[0-9]+$|", "a|^/dev/md[0-9]+p[0-9]+$|", "a|^/dev/sda[0-9]*$|","r|.*|" ]
  [ OK ]  global_filter:           global_filter = [ "a|^/dev/nvme[0-9]+n[0-9]+$|", "a|^/dev/nvme[0-9]+n[0-9]+p[0-9]+$|", "a|^/dev/md[0-9]+$|", "a|^/dev/md[0-9]+p[0-9]+$|", "a|^/dev/sda[0-9]*$|","r|.*|" ]

━━━  10. PF9 SERVICES ━━━
  [ OK ]  pf9-ostackhost.service: running
  [ OK ]  pf9-cindervolume-base.service: running
  [ OK ]  pf9-glance-api.service: running
  [ OK ]  pf9-comms.service: running
  [ OK ]  pf9-ha-slave.service: running
  [ OK ]  pf9-hostagent.service: running
  [ OK ]  pf9-libvirt-exporter.service: running
  [ OK ]  pf9-neutron-ovn-metadata-agent.service: running
  [ OK ]  pf9-node-exporter.service: running
  [ OK ]  pf9-novncproxy.service: running
  [ OK ]  pf9-prometheus.service: running
  [ OK ]  pf9-remote-write.service: running
  [ OK ]  pf9-sidekick.service: running

  [ nova_override.conf ]
  [ OK ]  volume_use_multipath: volume_use_multipath = True
  [ OK ]  iscsi_use_multipath: iscsi_use_multipath = True

             ── /opt/pf9/etc/nova/conf.d/nova_override.conf ──
             [libvirt]
             live_migration_uri = qemu+tls://%s/system?no_verify=1&pkipath=/etc/pf9/certs/libvirt
             cpu_mode = custom
             cpu_models = Icelake-Server-noTSX
             iscsi_use_multipath = True
             volume_use_multipath = True

             live_migration_scheme = tls
             live_migration_inbound_addr = xxx.xxx.xxx.xxx
             live_migration_with_native_tls = true
             live_migration_tunnelled = false

=== Totals VMs running on this hypervisor ===
num_vm_configs_local    1
total_vms_virsh:        1

  [ cinder.conf ]
  [ WARN ]  reserved_percentage not set in cinder.conf
  [ WARN ]  goodness_function not set in cinder.conf

━━━  11. OVS BRIDGES ━━━
  [ WARN ]  Bridge: br-int  (no IPv4 address)
             Ports: listing all ports on br-int (including virtual):
             tap04950ca9-7a
             tap05a770cd-4c
             tap11f23cfc-e3
             tap19d6c106-e8
             tap60635d0d-06
             tapec0a47a7-ca
  [ WARN ]  Bridge: br-phy1  (no IPv4 address)
             Physical ports: bond0
  [ OK ]  Bridge: br-phy2  IP: xxx.xxx.xxx.xx/24
             Physical ports: ens9f0
  [ OK ]  Bridge: br-phy4  IP: xxx.xxx.xxx.xxx/24
             Physical ports: vlan10

━━━  12. /ETC/HOSTS ━━━
  [ NOTE ]  Review and Ensure the SVM host IP mapping is set for the SVM FQDN to be resolvable

             127.0.0.1 localhost

             # The following lines are desirable for IPv6 capable hosts
             ::1     ip6-localhost ip6-loopback
             fe00::0 ip6-localnet
             ff00::0 ip6-mcastprefix
             ff02::1 ip6-allnodes
             ff02::2 ip6-allrouters

━━━  15. VIRSH LIVENESS ━━━
  [ OK ]  virsh is responsive
```

```bash
# Run all checks + passwordless sudo audit
sudo ./hostInfo-check.sh check-sudoers

━━━  1.  PASSWORDLESS SUDO ━━━
  [ OK ]  Users with passwordless sudo (14):
             pf9 (sudoers)
             cinder-rootwrap (/etc/sudoers.d/cinder-rootwrap)
             glance-rootwrap (/etc/sudoers.d/glance-rootwrap)
             nova-rootwrap (/etc/sudoers.d/nova-rootwrap)
             pf9-hostagent (/etc/sudoers.d/pf9-hostagent)
             pf9-neutron (/etc/sudoers.d/pf9-neutron)
             pf9-vmha-agent (/etc/sudoers.d/pf9-vmha-agent)
...
```

```bash
# Check for orphaned or faulty multipath devices
sudo ./hostInfo-check.sh check-mpath-orphan

━━━  13. MULTIPATH ORPHANS ━━━
  [ WARN ]  Orphan: 3600a098038314e65782b575176676b5a (dm-10) — not referenced by any VM XML
               3600a098038314e65782b575176676b5a dm-10 NETAPP,LUN C-Mode
               size=160G features='3 queue_if_no_path pg_init_retries 50' hwhandler='1 alua' wp=rw
               |-+- policy='service-time 0' prio=50 status=active
               | `- 17:0:0:14 sdf  8:80   active ready running
               `-+- policy='service-time 0' prio=10 status=enabled
                 `- 18:0:0:14 sdaa 65:160 active ready running
...
```

```bash
# List per-VM DM disks and multipath path state for all running VMs
sudo ./hostInfo-check.sh list-vm-mpath
...
━━━  14. VM DISK MULTIPATH ━━━

  VM: a66532c7-211f-48f2-be5e-6411ab93a605             UUID: a66532c7-211f-48f2-be5e-6411ab93a605
  [ OK ]  dm-16  →  3600a098038314e66303f575166592d48  active (2/2 paths up)

...
```

```bash
# Inspect VM disk/multipath mapping by UUID
sudo ./hostInfo-check.sh --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a
...
━━━  16. VIRSH VMS ━━━
  [ OK ]  VM: 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a  (UUID: 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a)
             Block device list:
                Type    Device   Target   Source
               ---------------------------------------
                block   disk     vda      /dev/dm-16
             Multipath mapping:
               dm-16  ->  3600a098038314e66303f575166592d48  (/dev/mapper/3600a098038314e66303f575166592d48)
...
```

```bash
# Full run: all host checks + sudoers + orphan check + VM mpath + VM inspection
sudo ./hostInfo-check.sh check-sudoers check-mpath-orphan list-vm-mpath --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a
```

### Requirements

- **OS:** Debian/Ubuntu (uses `dpkg`, `systemctl`, `timedatectl`)
- **Privileges:** Requires `root` or a user with access to `virsh`, `multipath`, `iscsiadm`, and `ovs-vsctl`
- **Conditional tools:** `virsh` (section 15 runs unconditionally but skips gracefully if absent; sections 14 and 16 require it for `list-vm-mpath` and `--uuid` respectively); `ovs-vsctl` (OVS check skipped gracefully if absent); `iscsid` (section 7 skipped if not installed)
