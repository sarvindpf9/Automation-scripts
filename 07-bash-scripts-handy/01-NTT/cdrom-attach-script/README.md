# attach-detach-cdrom-script

Orchestrator script to attach or detach Glance-backed ISO images to a running OpenStack VM via `virsh` over SSH. Resolves the target VM by IP through Nova, identifies its hypervisor, and performs the operation directly on the KVM host.

---

## `attach-detach-cdrom.sh`

The primary script. Handles both attach and detach in a single entry point.

**Dependencies (local):** `openstack` CLI, `ssh`, `python3`, sourced OpenStack credentials (`openrc` or environment variables)

**Dependencies (hypervisor):** `virsh`, NFS Glance mount accessible at `${NFS_GLANCE_MOUNT}` (default: `/var/opt/imagelibrary/data/glance`)

**What it does:**

1. Resolves the Nova instance UUID and name from the VM IP via `openstack server list` (scoped to the specified tenant via `OS_PROJECT_NAME`)
2. Resolves the hypervisor hostname and management IP via `openstack server show` + `openstack hypervisor list`
3. Runs pre-checks: VM state, hypervisor ICMP/SSH reachability, Glance image status (attach only)
4. Resolves the libvirt domain name on the hypervisor by matching `virsh domuuid` against the Nova instance UUID
5. Attaches or detaches CDROM device(s) via `virsh attach-disk` / `virsh detach-disk --live`

### Usage

```bash
# Attach one ISO
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --image-uuid <GLANCE_IMAGE_UUID>

# Attach two ISOs (e.g. OS installer + driver disk)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --image-uuid  <GLANCE_IMAGE_UUID_1> \
  --image-uuid2 <GLANCE_IMAGE_UUID_2>

# Detach all attached CDROMs
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME>

# Detach a specific CDROM device only
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --device <DEV>
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `--action attach\|detach` | Yes | Operation to perform |
| `--vm-ip IP` | One of these | IP address of the target VM |
| `--vm-name NAME` | One of these | Nova instance name of the target VM |
| `--user USER` | Yes | SSH username for the hypervisor |
| `--tenant NAME` | Yes | OpenStack project name; scopes the `server list --ip` lookup via `OS_PROJECT_NAME` |
| `--image-uuid UUID` | attach only | Glance image UUID for the first ISO |
| `--image-uuid2 UUID` | No | Glance image UUID for a second ISO (attach only, max 2 total) |
| `--device DEV` | No | Device name to selectively detach (e.g. `sdm`); detach only. Omit to detach all CDROMs. |
| `--nfs-mount PATH` | No | Override the NFS Glance mount path on the hypervisor (default: `/var/opt/imagelibrary/data/glance`). |
| `--virsh-as-root` | No | Run `virsh attach-disk` via `sudo su -` (full root login shell). Use when plain `sudo virsh` lacks the required environment on the hypervisor. Also applies to the NFS file accessibility check prior to attach. |
| `--help` | No | Show usage and exit |

### Examples

```bash
# Attach a Windows installer ISO to a VM at 10.0.1.50
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid e1a2b3c4-0000-0000-0000-win2022iso

# Attach OS ISO + VirtIO driver ISO simultaneously (by instance name)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-name win2022-prod-01 \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid  e1a2b3c4-0000-0000-0000-win2022iso \
  --image-uuid2 f5d6e7f8-0000-0000-0000-virtiodrivers

# Detach all CDROMs from the same VM
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --tenant <TENANT_NAME>

# Detach only the second CDROM (e.g. driver disk on sdn)
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --device sdn

# Attach using a full root login shell for virsh (when sudo alone is insufficient)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip 10.0.1.50 \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid e1a2b3c4-0000-0000-0000-win2022iso \
  --virsh-as-root
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

### CDROM hotplug compatibility: machine type requirements

`virsh attach-disk --live` requires a pre-existing CDROM slot in the VM's domain XML. Whether that slot can exist at all depends on the VM's emulated machine type.

#### i440fx (pc) — default for most existing VMs

The CDROM is emulated as an IDE device. IDE controllers in QEMU have **no hotplug support** — all slots must be defined at VM creation time. If the VM was provisioned without a CDROM device in its XML, live attach will fail with:

```text
error: Operation not supported: cdrom/floppy device hotplug isn't supported
```

To ensure a CDROM slot is present from provisioning, set the following property on the Glance image before booting the VM:

```bash
openstack image set <IMAGE_UUID> --property hw_cdrom_bus=scsi --property hw_disk_bus=virtio --property hw_machine_type=pc-i440fx-2.12 --property hw_scsi_model==virtio-scsi
```

This causes Nova to include an empty IDE CDROM device in the domain XML at boot, giving libvirt a slot to target at hotplug time. Without it, the only option is cold attach (`--config` without `--live`, requiring a reboot).


#### q35 — recommended for new VM deployments

q35 uses a PCIe bus with an ICH9 chipset. The CDROM is backed by a SATA controller (`ich9-ahci`), which **does support hotplug** at the controller level. This removes the architectural blocker present on i440fx.

Set the following properties on the Glance image to provision a q35 VM with a SATA CDROM slot:

```bash
openstack image set <IMAGE_UUID> \
  --property hw_machine_type=q35 \
  --property hw_cdrom_bus=sata
```

The `hw_cdrom_bus=sata` property ensures the CDROM device is attached to the ICH9 SATA controller rather than falling back to IDE. Without it, Nova may still place the CDROM on an IDE bus even on q35, which reintroduces the hotplug limitation.

Alternatively, set these on a flavor to apply across all VMs using it:

```bash
openstack flavor set <FLAVOR> \
  --property hw:machine_type=q35 \
  --property hw:cdrom_bus=sata
```

> **Note:** Machine type is baked in at VM creation. Existing i440fx VMs cannot be converted to q35 in-place — a rebuild is required. For existing VMs without a CDROM slot, cold attach remains the only viable option.