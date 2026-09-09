# hostcheck-script

Local health-check utility for supported Platform9 KVM compute hosts.

---

## `hostInfo_check-v2.sh`

`hostInfo_check-v2.sh` inspects the local host's operating system, networking, time synchronization, storage configuration, Platform9 packages and services, libvirt state, and supporting system configuration. It does not modify host configuration, but some checks print complete configuration or account records and therefore its output should be handled as operationally sensitive.

<!-- The output can contain hostnames, IP addresses, iSCSI initiator IQNs, VM UUIDs, account records, storage identifiers, and configuration-file contents. Review and redact logs before sharing them. -->

**Dependencies (local):**

- Bash with associative-array and `mapfile` support; the script uses `set -euo pipefail`
- A readable `/etc/os-release`; supported OS IDs are `ubuntu`, `rocky`, `rhel`, and `almalinux`
- `dpkg-query` on Ubuntu or `rpm` on Rocky Linux, RHEL, and AlmaLinux
- Standard utilities used by the checks: `awk`, `grep`, `sed`, `find`, `stat`, `getent`, `grpck`, `ip`, `timedatectl`, `systemctl`, `timeout`, and `ps`
- Storage and virtualization commands used where applicable: `iscsiadm`, `multipath`, `ovs-vsctl`, and `virsh`
- Root or equivalent read access is recommended because the script reads system, Platform9, libvirt, multipath, iSCSI, sudoers, and service configuration

**What it does:**

1. Detects the operating system and selects the Debian or RPM package-query backend. It exits with status `2` if OS detection fails, the OS is unsupported, or the required package-query command is unavailable.
2. Runs one of three mutually exclusive modes: the requested standalone check(s) (`check-mpath-orphan`, `list-vm-mpath`, `check-glance-mount`), the single `VIRSH VMS` check when only `--uuid` is given, or the full default host-check suite.
3. Reports results as `[ OK ]`, `[ FAIL ]`, `[ WARN ]`, `[ NOTE ]`, and informational lines. Individual check failures normally do not determine the script's exit status because each health-check function is invoked with failure suppression.
4. Optionally writes combined standard output and standard error to a log while continuing to display coloured output in the terminal. ANSI colour codes are removed from the file.

### Usage

```bash
# Make the script executable if required
chmod +x hostInfo_check-v2.sh

# Run the full default host-check suite
sudo ./hostInfo_check-v2.sh

# Add the passwordless-sudo check to the full default suite
sudo ./hostInfo_check-v2.sh check-sudoers

# Run only the VM block-device / multipath check for one VM (by UUID)
sudo ./hostInfo_check-v2.sh --uuid <VM_UUID>

# Run only the multipath-orphan check
sudo ./hostInfo_check-v2.sh check-mpath-orphan

# Run only the per-VM multipath check
sudo ./hostInfo_check-v2.sh list-vm-mpath

# Run only the Glance image-library mount check using its default directory
sudo ./hostInfo_check-v2.sh check-glance-mount

# Run only the Glance mount check for a specified absolute directory
sudo ./hostInfo_check-v2.sh check-glance-mount <GLANCE_MOUNT_DIRECTORY>

# Write the full-suite output to an automatically named log
sudo ./hostInfo_check-v2.sh --log

# Write the full-suite output to a specified file
sudo ./hostInfo_check-v2.sh --output <OUTPUT_FILE>
```

Dispatch is mutually exclusive across three modes, evaluated in this order:

1. If any standalone selector (`check-mpath-orphan`, `list-vm-mpath`, `check-glance-mount`) is present, the script runs only the selected standalone check(s) and skips everything else, including `check-sudoers` and `--uuid`.
2. Otherwise, if `--uuid <VM_UUID>` is present, the script runs only the `VIRSH VMS` check for that VM and skips the full default suite.
3. Otherwise, the script runs the full default suite (with `check-sudoers` added if requested).

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `--uuid <VM_UUID>` | No | Standalone `VIRSH VMS` mode when no other selector is present: resolves the UUID with `virsh`, prints the VM's block-device list, and maps any `dm-*` devices to multipath maps. Ignored if `check-mpath-orphan`, `list-vm-mpath`, or `check-glance-mount` is also given. A missing value exits with status `2`. |
| `--virsh` | No | Accepted for backward compatibility and otherwise has no effect. `--uuid` enables the VM-specific check. |
| `check-sudoers` | No | Adds a scan for exact `NOPASSWD: ALL` user entries in `/etc/sudoers` and readable files under `/etc/sudoers.d`. Applies only to the full suite. |
| `check-mpath-orphan` | No | Standalone selector. Reports multipath maps not referenced by libvirt VM XML and reports `failed` or `faulty` paths. |
| `list-vm-mpath` | No | Standalone selector. Lists each running VM's device-mapper disks and classifies their multipath paths as active, degraded, or dead. |
| `check-glance-mount [directory]` | No | Standalone selector. Checks `/etc/fstab`, mode `755`, and ownership `pf9:pf9group`. The directory defaults to `/var/opt/imagelibrary/`. |
| `--log` | No | Writes to `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory. |
| `--output <OUTPUT_FILE>` | No | Writes to the specified path, overwriting an existing file before appending check output. A missing value exits with status `2`. |

Unknown arguments print usage information and exit with status `1`.

### Default checks

The following checks run when no standalone selector is supplied:

| Check | Behaviour |
| ---- | ----------- |
| Operating system | Reports the detected OS. Ubuntu uses Debian package names; Rocky Linux, RHEL, and AlmaLinux use RPM package names and command-provider checks where package names vary. |
| Bond interfaces | Finds Linux bond interfaces, reports their IPv4 addresses, and warns when a bond is not using `802.3ad`. |
| NTP | Requires `timedatectl` to report `NTPSynchronized=yes`. |
| Host packages | Checks the distribution-appropriate SCSI, multipath, iSCSI, and NFS client packages or commands. |
| Core services | Checks whether `iscsid` and `multipathd` are installed and active. |
| iSCSI initiator | Reads `/etc/iscsi/initiatorname.iscsi`, reports the initiator name, and lists active iSCSI sessions when `iscsid` is running. |
| iSCSI configuration | Checks five timeout settings in `/etc/iscsi/iscsid.conf`: replacement `15`, login `5`, logout `5`, abort `10`, and LU reset `20`. |
| Multipath configuration | Requires `/etc/multipath.conf`; expects `checker_timeout 15`, reports blacklist entries, validates the NETAPP device stanza, and prints the complete file. |
| LVM filters | Reports configured `filter` and `global_filter` entries from `/etc/lvm/lvm.conf`. |
| Platform9 packages | Checks Open vSwitch/OVN prerequisites and the Platform9 compute/storage package set encoded in the script. |
| Platform9 services | Reports the Platform9 service set. When `pf9-ostackhost` is active, it checks `volume_use_multipath`, prints `nova_override.conf`, and compares local libvirt XML names with `virsh`. When `pf9-cindervolume-base` is active, it prints `cinder_override.conf`. |
| OVS bridges | Lists bridges, IPv4 addresses, all `br-int` ports, and likely physical ports on other bridges. |
| `/etc/hosts` | Prints an advisory about required host mappings and then prints the complete file. |
| Virsh liveness | Requires `virsh list --all` to finish within 10 seconds. On failure, it searches for zombie QEMU processes and reports associated VM and multipath information when resolvable. |
| Group database | Runs the read-only `grpck -r` consistency check. |
| Platform9 rsyslog rules | Searches `/etc/rsyslog.d` for rules targeting the six Platform9 log paths encoded in the script. |
| Platform9 account | Reports whether the `pf9` user and `pf9group` group exist and prints their `getent` records. |

`--uuid` is not part of this table: it is a separate standalone mode (see below), not an addition to the default suite.

### Standalone-check behaviour

| Check | Applies to |
| ---- | ---------- |
| Compare every multipath `dm-*` map with disk sources in `/etc/libvirt/qemu/*.xml`; report unreferenced maps and failed/faulty paths | `check-mpath-orphan` only |
| Query running VMs, use `virsh domblklist --details` (falling back to the VM's libvirt XML) to find each disk's `dm-*` device — resolving `/dev/mapper/*` and `/dev/disk/by-id/dm-uuid-mpath-*`/other by-id aliases to their real `dm-N` node via `readlink -f` — then report each multipath map as active, degraded, dead, or missing | `list-vm-mpath` only |
| Normalize the requested directory, find a matching mount point at or below it in `/etc/fstab`, then require mode `755` and owner/group `pf9:pf9group` if the directory exists | `check-glance-mount` only |
| Resolve the UUID with `virsh domname`, print the VM's `virsh domblklist --details` block-device list, then map any `dm-*` device found in the `Source` column to its multipath map | `--uuid <VM_UUID>` only (skipped if any selector above is also given) |

Unlike `list-vm-mpath`, the `--uuid` block-device mapping does **not** resolve `/dev/mapper/*` or `/dev/disk/by-id/*` sources to a `dm-N` device — it only matches a `Source` value that already contains a literal `dm-<digits>`. If disks are attached via `/dev/disk/by-id/dm-uuid-mpath-*` (the Cinder/Ceph RBD multipath convention), `--uuid` prints the block-device list correctly but then reports `No dm-* devices found for <vm> (can be ignored of disk/by-id mpath devices are visible)` for the multipath-mapping step — use `list-vm-mpath` instead to get the resolved multipath state in that case.

The standalone selectors can be combined in one invocation:

```bash
# Run all three standalone checks and write their output to one file
sudo ./hostInfo_check-v2.sh \
  check-mpath-orphan \
  list-vm-mpath \
  check-glance-mount <GLANCE_MOUNT_DIRECTORY> \
  --output <OUTPUT_FILE>
```

### Output and exit behaviour

- Without `--log` or `--output`, output is written only to the terminal.
- With logging enabled, the output file begins with the short hostname and timestamp. Terminal output remains coloured; the file is plain text.
- The script is primarily a reporting tool. Read `[ FAIL ]` and `[ WARN ]` lines to determine host health; a completed run can exit successfully even when checks report failures.
- Invocation and environment validation errors use non-zero exit codes: unknown argument `1`; missing option value, unreadable OS metadata, unsupported OS, or missing package backend `2`.
- `--output` truncates an existing target file. Use a new path if existing output must be preserved.

### Sensitive output

The report can include hostnames, IP addresses, iSCSI initiator names and sessions, multipath identifiers and full stanzas, VM names and UUIDs, `/etc/hosts`, Platform9 configuration files, sudoers matches, and local account entries. Review and redact the output before attaching it to tickets or sharing it outside the authorized operations team.
