# attach-detach-cdrom-script

Orchestrator script to attach or detach ISO images to a running OpenStack VM via `virsh` over SSH. Supports both Glance-backed ISOs (resolved by UUID from an NFS Glance mount) and locally-hosted ISOs present on the target hypervisor. Resolves the target VM by IP or name through Nova, identifies its hypervisor, and performs the operation directly on the KVM host.

> [!WARNING]
> **Hypervisor OS compatibility:** This script is tested and fully functional on **Ubuntu 24.04 LTS** hypervisors. It will **not work** on **Ubuntu 22.04-based hypervisors** due to the older versions of QEMU and libvirt shipped with that release — specifically, the `virsh attach-disk --live` hotplug path relies on capabilities (SCSI/SATA CDROM hotplug, domain XML update semantics) that are either absent or broken in the QEMU/libvirt versions bundled with Ubuntu 22.04. Upgrade the hypervisor OS to Ubuntu 24.04 before using this script.

---

## `attach-detach-cdrom.sh`

The primary script. Handles both attach and detach in a single entry point, with two mutually exclusive attach modes: Glance UUID mode and local ISO mode.

**Dependencies (local):**

- `openstack` CLI, `ssh`, `python3`, sourced OpenStack credentials on the host used as the control host for executing this script.
- The local host must have SSH key-based access to every hypervisor in the cluster with a passwordless sudo user.
- Admin-level OpenStack credentials are required to resolve hypervisor attributes.

**Dependencies (hypervisor):**

- `virsh` and `sudo` access for the connecting SSH user.
- **Glance mode:** NFS Glance mount accessible at `${NFS_GLANCE_MOUNT}` (default: `/var/opt/imagelibrary/data/glance`).
- **Local ISO mode:** ISO files present at the specified directory path on the hypervisor; no NFS Glance mount required.

**What it does:**

1. Resolves the Nova instance UUID and name from the VM IP via `openstack server list` (scoped to the specified tenant via `OS_PROJECT_NAME`), or directly by name via `openstack server show`
2. Resolves the hypervisor hostname and management IP via `openstack server show` + `openstack hypervisor list`
3. Runs pre-checks: VM state, hypervisor ICMP/SSH reachability; then Glance image status (Glance mode) or directory and ISO file existence on the hypervisor (local ISO mode) — attach only
4. Resolves the libvirt domain name on the hypervisor by matching `virsh domuuid` against the Nova instance UUID
5. Attaches or detaches CDROM device(s) via `virsh attach-disk` / `virsh detach-disk --live`

### Usage

```bash
# Attach one ISO (Glance mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --image-uuid <GLANCE_IMAGE_UUID>

# Attach two ISOs (Glance mode — e.g. OS installer + driver disk)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --image-uuid  <GLANCE_IMAGE_UUID_1> \
  --image-uuid2 <GLANCE_IMAGE_UUID_2>

# Attach one ISO from a local directory on the hypervisor (local ISO mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --iso-dir <ISO_DIRECTORY_PATH> \
  --iso-name <ISO_FILENAME>

# Attach two ISOs from the same local directory (local ISO mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user <SSH_USER> \
  --tenant <TENANT_NAME> \
  --iso-dir <ISO_DIRECTORY_PATH> \
  --iso-name  <ISO_FILENAME_1> \
  --iso-name2 <ISO_FILENAME_2>

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
| ---- | -------- | ----------- |
| `--action attach\|detach` | Yes | Operation to perform |
| `--vm-ip IP` | One of these | IP address of the target VM |
| `--vm-name NAME` | One of these | Nova instance name of the target VM |
| `--user USER` | Yes | SSH username for the hypervisor |
| `--tenant NAME` | Yes | OpenStack project name; scopes the `server list --ip` lookup via `OS_PROJECT_NAME` |
| `--image-uuid UUID` | attach only (Glance mode) | Glance image UUID for the first ISO. Mutually exclusive with `--iso-dir`. |
| `--image-uuid2 UUID` | No | Glance image UUID for a second ISO (Glance mode, attach only, max 2 total) |
| `--iso-dir PATH` | attach only (local ISO mode) | Absolute path to a directory on the hypervisor containing ISO files. Mutually exclusive with `--image-uuid`. |
| `--iso-name FILE` | attach only (local ISO mode) | ISO filename within `--iso-dir` to attach. Required when `--iso-dir` is set. |
| `--iso-name2 FILE` | No | Second ISO filename within `--iso-dir` (local ISO mode, attach only, max 2 total) |
| `--device DEV` | No | Device name to selectively detach (e.g. `sdm`); detach only. Omit to detach all CDROMs. |
| `--nfs-mount PATH` | No | Override the NFS Glance mount base directory on the hypervisor (default: `/var/opt/imagelibrary/data/glance`). Glance mode only; the image UUID is appended to this path. |
| `--virsh-as-root` | No | Run `virsh attach-disk` via `sudo su -` (full root login shell). Use when plain `sudo virsh` lacks the required environment on the hypervisor. Also applies to the ISO file accessibility check prior to attach. |
| `--help` | No | Show usage and exit |

### Examples

```bash
# Attach a Windows installer ISO to a VM by IP (Glance mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid <GLANCE_IMAGE_UUID>

# Attach OS ISO + VirtIO driver ISO simultaneously by instance name (Glance mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-name <VM_NAME> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid  <GLANCE_IMAGE_UUID_1> \
  --image-uuid2 <GLANCE_IMAGE_UUID_2>

# Attach a customer-supplied ISO from a local directory on the hypervisor (local ISO mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --iso-dir /mnt/customer-isos \
  --iso-name rhel9.iso

# Attach two ISOs from the same local directory (local ISO mode)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-name <VM_NAME> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --iso-dir /mnt/customer-isos \
  --iso-name  rhel9.iso \
  --iso-name2 drivers.iso

# Detach all CDROMs from a VM
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user ubuntu \
  --tenant <TENANT_NAME>

# Detach only the second CDROM (e.g. driver disk on sdn)
./attach-detach-cdrom.sh \
  --action detach \
  --vm-ip <VM_IP> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --device sdn

# Attach using a full root login shell for virsh (when plain sudo is insufficient)
./attach-detach-cdrom.sh \
  --action attach \
  --vm-ip <VM_IP> \
  --user ubuntu \
  --tenant <TENANT_NAME> \
  --image-uuid <GLANCE_IMAGE_UUID> \
  --virsh-as-root
```

### CDROM device assignment

Devices are allocated in preference order: `sdm → sdn → sdo → sdp`. Starting at `sdm` avoids conflicts with primary OS and data disks which typically occupy the lower `sd*` slots. The first device not already in use by the domain is selected for each ISO.

Detach without `--device` removes all CDROMs reported by `virsh domblklist`; it will refuse if more than 2 are found (unexpected state — investigate manually). With `--device`, only the named device is detached; the script validates it is an attached CDROM on the domain before proceeding.

### Pre-check behaviour

All pre-checks run before any `virsh` command is issued. Failure in any check aborts the script cleanly:

| Check | Applies to |
| ----- | ---------- |
| Nova instance is `ACTIVE`, `SHUTOFF`, `PAUSED`, or `SUSPENDED` | attach + detach |
| Hypervisor reachable via ICMP | attach + detach |
| Hypervisor reachable via SSH | attach + detach |
| Glance image exists and is `active` | attach only (Glance mode) |
| Directory exists on hypervisor at `--iso-dir` path | attach only (local ISO mode) |
| ISO file exists within `--iso-dir` on the hypervisor | attach only (local ISO mode) |

In local ISO mode, the Glance UUID validation is skipped entirely — no `openstack image show` call is made. The directory check runs before the file check; if the directory is absent the script aborts without attempting the file check.

### CDROM hotplug compatibility: machine type requirements

`virsh attach-disk --live` requires a pre-existing CDROM slot in the VM's domain XML. Whether that slot can exist at all depends on the VM's emulated machine type.

#### i440fx (pc) — default for most existing VMs

The CDROM is emulated as an IDE device. IDE controllers in QEMU have **no hotplug support** — all slots must be defined at VM creation time with SATA mode. If the VM was provisioned without a CDROM device in its XML in default cases, live attach will fail with:

```text
error: Operation not supported: cdrom/floppy device hotplug isn't supported
```

To ensure a CDROM slot is present from provisioning, set the following property on the Glance image before booting the VM:

```bash
openstack image set <IMAGE_UUID> --property hw_cdrom_bus=scsi --property hw_disk_bus=virtio --property hw_scsi_model=virtio-scsi
```

> **Note:**
>
> - `--property hw_machine_type=pc-i440fx` is not required as Nova will pick it automatically if no machine type is defined.
> - CDROM bus as `SATA` may not emulate correctly with the default `i440fx` machine type; `SCSI` mode is recommended.

This causes Nova to include an empty SCSI CDROM device in the domain XML at boot, giving libvirt a slot to target at hotplug time. Without it, the only option is cold attach (`--config` without `--live`, requiring a reboot).

#### q35 — recommended for new VM deployments

q35 uses a PCIe bus with an ICH9 chipset. The CDROM is backed by a SATA controller (`ich9-ahci`), which **does support hotplug** at the controller level. This removes the architectural blocker present on i440fx.

Set the following properties on the Glance image to provision a q35 VM with a SATA CDROM slot:

```bash
openstack image set <IMAGE_UUID> --property hw_machine_type=q35 --property hw_cdrom_bus=sata --property hw_disk_bus=virtio --property hw_scsi_model=virtio-scsi
```

The `hw_cdrom_bus=sata` property ensures the CDROM device is attached to the ICH9 SATA controller rather than falling back to IDE. Without it, Nova may still place the CDROM on an IDE bus even on q35, which reintroduces the hotplug limitation.

Alternatively, set these on a flavor to apply across all VMs using it:

```bash
openstack flavor set <FLAVOR> \
  --property hw:machine_type=q35 \
  --property hw:cdrom_bus=sata
```

> **Note:** Machine type is baked in at VM creation. Existing i440fx VMs cannot be converted to q35 in-place — a rebuild is required. For existing VMs without a CDROM slot, the recommended approach is to rebuild the VM with the required image properties set on the boot volume and use it as the base for cloning/snapshotting.

#### Verification

Once the ISO is attached successfully, run the following from the hypervisor to confirm the CDROM device appears in the domain's block list:

```
virsh domblklist <INSTANCE_UUID> --details
 Type   Device   Target   Source
--------------------------------------------------------------------------------------------------------------------------------
 file   disk     vda      /opt/pf9/data/state/mnt/<VOL_BACKING_PATH>/volume-<VOLUME_UUID>
 file   cdrom    sdm      /var/opt/imagelibrary/data/glance/<GLANCE_IMAGE_UUID>
```

<!-- NOTE: Replace <INSTANCE_UUID>, <VOL_BACKING_PATH>, <VOLUME_UUID>, and <GLANCE_IMAGE_UUID> with actual values from your environment. Do not commit real UUIDs or paths to this file. -->

#### Example outputs

<!-- NOTE: IP addresses, hostnames, VM names, and UUIDs below are redacted. Replace placeholders with actual values when sharing internally. -->

- Attach by VM name (Glance mode):

```
./attach-detach-cdrom.sh --action attach --vm-name <VM_NAME> --image-uuid <GLANCE_IMAGE_UUID> --user ubuntu --tenant <TENANT_NAME>
Resolving instance by name '<VM_NAME>' ...
Instance:   <VM_NAME> (<INSTANCE_UUID>)
Resolving hypervisor for instance <INSTANCE_UUID> ...
  Hypervisor hostname: <HV_HOSTNAME>
  Hypervisor IP:       <HV_IP>
Hypervisor: <HV_HOSTNAME> (<HV_IP>)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor <HV_IP> is reachable via ICMP.
  [OK] SSH to ubuntu@<HV_IP> succeeded.
  [OK] Image <GLANCE_IMAGE_UUID> status: active
  All pre-checks passed.

Domain:     <INSTANCE_UUID>

Attaching /var/opt/imagelibrary/data/glance/<GLANCE_IMAGE_UUID> to domain <INSTANCE_UUID> as sdm ...
Disk attached successfully

Attached successfully.
  INSTANCE=<INSTANCE_UUID>
  DOMAIN=<INSTANCE_UUID>
  DEVICE=/dev/sdm
  ISO=/var/opt/imagelibrary/data/glance/<GLANCE_IMAGE_UUID>

Done. 1 ISO(s) attached to <INSTANCE_UUID>.
```

- Attach from a local directory on the hypervisor (local ISO mode):

```
./attach-detach-cdrom.sh --action attach --vm-name <VM_NAME> --user ubuntu --tenant <TENANT_NAME> --iso-dir /mnt/customer-isos --iso-name rhel9.iso
Resolving instance by name '<VM_NAME>' ...
Instance:   <VM_NAME> (<INSTANCE_UUID>)
Resolving hypervisor for instance <INSTANCE_UUID> ...
  Hypervisor hostname: <HV_HOSTNAME>
  Hypervisor IP:       <HV_IP>
Hypervisor: <HV_HOSTNAME> (<HV_IP>)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor <HV_IP> is reachable via ICMP.
  [OK] SSH to ubuntu@<HV_IP> succeeded.
  [OK] Directory /mnt/customer-isos exists on <HV_IP>.
  [OK] ISO rhel9.iso found at /mnt/customer-isos/rhel9.iso on <HV_IP>.

Domain:     <INSTANCE_UUID>

Attaching /mnt/customer-isos/rhel9.iso to domain <INSTANCE_UUID> as sdm ...
Disk attached successfully

Attached successfully.
  INSTANCE=<INSTANCE_UUID>
  DOMAIN=<INSTANCE_UUID>
  DEVICE=/dev/sdm
  ISO=/mnt/customer-isos/rhel9.iso

Done. 1 ISO(s) attached to <INSTANCE_UUID>.
```

- Detach all CDROMs:

```
./attach-detach-cdrom.sh --action detach --vm-ip <VM_IP> --user ubuntu --tenant <TENANT_NAME>
Resolving instance for IP <VM_IP> ...
Instance:   <VM_NAME> (<INSTANCE_UUID>)
Resolving hypervisor for instance <INSTANCE_UUID> ...
  Hypervisor hostname: <HV_HOSTNAME>
  Hypervisor IP:       <HV_IP>
Hypervisor: <HV_HOSTNAME> (<HV_IP>)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor <HV_IP> is reachable via ICMP.
  [OK] SSH to ubuntu@<HV_IP> succeeded.
  All pre-checks passed.

Domain:     <INSTANCE_UUID>

Detaching sdm (cdrom) from domain <INSTANCE_UUID> ...
Disk detached successfully

Detached successfully.
  INSTANCE=<INSTANCE_UUID>
  DOMAIN=<INSTANCE_UUID>
  DEVICE=/dev/sdm
  NOTE: Glance image on NFS is unaffected.

Done. 1 ISO(s) detached from <INSTANCE_UUID>.
```

- Multiple VMs match the specified IP — the script prompts for a selection:

```text
./attach-detach-cdrom.sh --action attach --vm-ip <VM_IP> --image-uuid <GLANCE_IMAGE_UUID> --user ubuntu --tenant <TENANT_NAME>
Resolving instance for IP <VM_IP> (tenant: <TENANT_NAME>) ...
Multiple instances match IP '<VM_IP>':
  1) <INSTANCE_UUID_1>  <VM_NAME_1>
  2) <INSTANCE_UUID_2>  <VM_NAME_2>
  3) <INSTANCE_UUID_3>  <VM_NAME_3>
  4) <INSTANCE_UUID_4>  <VM_NAME_4>
Select instance [1-4]: 1
Instance:   <VM_NAME_1> (<INSTANCE_UUID_1>)
...
```
