# hostInfo-check.sh

Host health-check script for OpenStack KVM compute nodes. Validates storage, networking, and platform services required for stable hypervisor operation.

---

## Usage

```bash
# Run all host checks against one or more IPs useful fo verify netapp SVM entries
./hostInfo-check.sh <ip1> [ip2] ...

# Check virsh VM disk/multipath only
./hostInfo-check.sh --uuid <vm-uuid>

# Run all checks including virsh
./hostInfo-check.sh <ip1> [ip2] ... --uuid <vm-uuid>
```

**At least one argument is required** — either an IP or `--uuid`. The script exits with usage if called with no arguments.

---

## Checks Performed

### When one or more IPs are passed

| # | Section | What it checks |
| - | ------- | -------------- |
| 1 | **Passwordless sudo** | Scans `/etc/sudoers` and `/etc/sudoers.d/*` for users with `ALL=(ALL) NOPASSWD: ALL` |
| 2 | **Bond mode** | Detects all `type bond` interfaces; flags any not in `802.3ad` (LACP) mode; prints IP per bond |
| 3 | **NTP** | `timedatectl` — verifies NTP is active **and** system clock is synchronized |
| 4 | **Packages** | Checks `dpkg -l` for: `lsscsi`, `sg3-utils`, `multipath-tools`, `scsitools`, `open-iscsi`, `nfs-common` |
| 5 | **Services** | `systemctl is-active` for: `iscsid`, `multipathd` |
| 6 | **iSCSI initiator** | Reads `/etc/iscsi/initiatorname.iscsi`; lists active iSCSI sessions via `iscsiadm -m session` |
| 7 | **Multipath blacklist** | Parses `/etc/multipath.conf` blacklist block for `devnode`/`wwid`/`device` entries |
| 8 | **LVM filters** | Checks `/etc/lvm/lvm.conf` for `filter` and `global_filter` stanzas |
| 9 | **`/etc/hosts`** | Verifies each supplied IP is present as a full-word match in `/etc/hosts` |
| 10 | **PF9 services** | `systemctl` status for: `pf9-ostackhost`, `pf9-cindervolume-base`, `pf9-glance-api` |
| 11 | **OVS bridges** | Lists all OVS bridges, their IPv4 addresses, and physical uplink ports (skips `patch`/`internal` types and `br-int` port enumeration) |

### When `--uuid` is passed

| # | Section | What it checks |
| - | ------- | -------------- |
| 12 | **Virsh VM** | Resolves UUID to domain name; lists block devices via `virsh domblklist --details`; maps `dm-*` devices to `/dev/mapper/<name>` entries via `multipath -ll` |

---

## Output Format

Each result line is prefixed with a status badge:

| Badge | Meaning |
| ----- | ------- |
| `[ OK ]` (green) | Check passed |
| `[ FAIL ]` (red) | Check failed or resource missing |
| `[ WARN ]` (yellow) | Unexpected but non-fatal state |
| (dim indent) | Informational detail line |

Sections are separated by a cyan header banner.

---

## Requirements

- **OS:** Debian/Ubuntu (uses `dpkg`, `systemctl`, `timedatectl`)
- **Privileges:** Most checks require `root` or a user with `sudo` access to `virsh`, `multipath`, `iscsiadm`, and `ovs-vsctl`
- **Tools (conditional):** `virsh` (only needed with `--uuid`), `ovs-vsctl` (OVS check will FAIL gracefully if absent)

---

## Examples

```bash
# Check host, confirming two IPs are in /etc/hosts
sudo ./hostInfo-check.sh 10.0.1.10 10.0.1.11

# Inspect VM disk/multipath mapping by UUID
sudo ./hostInfo-check.sh --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a

# Full check: host + VM
sudo ./hostInfo-check.sh 10.0.1.10 --uuid 4a2f1c3d-7e8b-4d5a-9f0e-1b2c3d4e5f6a
```
