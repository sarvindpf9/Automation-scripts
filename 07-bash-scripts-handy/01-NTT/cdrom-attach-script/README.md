# attach-detach-cdrom-script

Orchestrator script to attach or detach Glance-backed ISO images to a running OpenStack VM via `virsh` over SSH. Resolves the target VM by IP through Nova, identifies its hypervisor, and performs the operation directly on the KVM host.

---

## `cd-attachment.sh`

The primary script. Handles both attach and detach in a single entry point.

**Dependencies (local):** `openstack` CLI, `ssh`, `python3`, sourced OpenStack credentials (`openrc` or environment variables)

**Dependencies (hypervisor):** `virsh`, NFS Glance mount accessible at `${NFS_GLANCE_MOUNT}` (default: `/var/opt/imagelibrary/data/glance`)

**What it does:**

1. Resolves the Nova instance UUID and name from the VM IP via `openstack server list`
2. Resolves the hypervisor hostname and management IP via `openstack server show` + `openstack hypervisor list`
3. Runs pre-checks: VM state, hypervisor ICMP/SSH reachability, Glance image status (attach only)
4. Resolves the libvirt domain name on the hypervisor by matching `virsh domuuid` against the Nova instance UUID
5. Attaches or detaches CDROM device(s) via `virsh attach-disk` / `virsh detach-disk --live`

### Usage

```bash
# Attach one ISO
./cd-attachment.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --image-uuid <GLANCE_IMAGE_UUID>

# Attach two ISOs (e.g. OS installer + driver disk)
./cd-attachment.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --image-uuid  <GLANCE_IMAGE_UUID_1> \
  --image-uuid2 <GLANCE_IMAGE_UUID_2>

# Detach all attached CDROMs
./cd-attachment.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user <SSH_USER>

# Detach a specific CDROM device only
./cd-attachment.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --device <DEV>
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `--action attach\|detach` | Yes | Operation to perform |
| `--vm-ip IP` | One of these | IP address of the target VM |
| `--vm-name NAME` | One of these | Nova instance name of the target VM |
| `--user USER` | Yes | SSH username for the hypervisor |
| `--image-uuid UUID` | attach only | Glance image UUID for the first ISO |
| `--image-uuid2 UUID` | No | Glance image UUID for a second ISO (attach only, max 2 total) |
| `--device DEV` | No | Device name to selectively detach (e.g. `sdm`); detach only. Omit to detach all CDROMs. |
| `--help` | No | Show usage and exit |

### Examples

```bash
# Attach a Windows installer ISO to a VM at 10.0.1.50
./cd-attachment.sh \
  --action attach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --image-uuid e1a2b3c4-0000-0000-0000-win2022iso

# Attach OS ISO + VirtIO driver ISO simultaneously (by instance name)
./cd-attachment.sh \
  --action attach \
  --vm-name win2022-prod-01 \
  --user ubuntu \
  --image-uuid  e1a2b3c4-0000-0000-0000-win2022iso \
  --image-uuid2 f5d6e7f8-0000-0000-0000-virtiodrivers

# Detach all CDROMs from the same VM
./cd-attachment.sh \
  --action detach \
  --vm-ip 10.0.1.50 \
  --user ubuntu

# Detach only the second CDROM (e.g. driver disk on sdn)
./cd-attachment.sh \
  --action detach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --device sdn
```

### CDROM device assignment

Devices are allocated in preference order: `sdm → sdn → sdo → sdp`. Starting at `sdm` avoids conflicts with primary OS and data disks which typically occupy the lower `sd*` slots. The first device not already in use by the domain is selected for each ISO.

Detach without `--device` removes all CDROMs reported by `virsh domblklist`; it will refuse if more than 2 are found (unexpected state — investigate manually). With `--device`, only the named device is detached; the script validates it is an attached CDROM on the domain before proceeding.

### Pre-check behaviour

All pre-checks run before any `virsh` command is issued. Failure in any check aborts the script cleanly:

| Check | Applies to |
|-------|-----------|
| Nova instance is `ACTIVE`, `SHUTOFF`, `PAUSED`, or `SUSPENDED` | attach + detach |
| Hypervisor reachable via ICMP | attach + detach |
| Hypervisor reachable via SSH | attach + detach |
| Glance image exists and is `active` | attach only |

---

## `attach-cdrom.sh` / `detach-cdrom.sh`

Simpler, standalone wrappers for individual attach and detach operations. Refer to the inline usage comments in each script for arguments — `cd-attachment.sh` is the preferred entry point for new usage.

---

## Prerequisites Summary

| Requirement | Detail |
|-------------|--------|
| Run from | Jump host / workstation with OpenStack credentials sourced |
| SSH access | Key-based, `BatchMode=yes` — interactive password auth is not supported |
| Hypervisor user | Must have permission to run `virsh` commands (typically `root` or a user in the `libvirt` group) |
| NFS Glance mount | Must be mounted on the hypervisor at `/var/opt/imagelibrary/data/glance` (override `NFS_GLANCE_MOUNT` in script if different) |
| OpenStack role | Needs `admin` or `reader` on the project to read `OS-EXT-SRV-ATTR:hypervisor_hostname` from `server show` |
