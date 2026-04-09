# attach-detach-cdrom-script

Orchestrator script to attach or detach Glance-backed ISO images to a running OpenStack VM via `virsh` over SSH. Resolves the target VM by IP through Nova, identifies its hypervisor, and performs the operation directly on the KVM host.

---

## `attach-detach-cdrom.sh`

The primary script. Handles both attach and detach in a single entry point.

**Dependencies (local):** 
- `openstack` CLI, `ssh`, `python3`, sourced OpenStack credentials on the host to be used as control host for executing this script.
- The local host should have access to use passwordless sudo user to connect to every hypervisors in the cluster and execute sudo command without passwords. SSH key based authentication is the recommended approach.
- The jump/control host should be able to access the hypervisor IP over ssh.
- The script requires admin user credentials to execute this task.
  
**Dependencies (hypervisor):**
-  `virsh`, NFS Glance mount accessible at `${NFS_GLANCE_MOUNT}` (default: `/var/opt/imagelibrary/data/glance`). This can be any mount location where the ISO file is accessible to all of the hypervisors.
- A sudo passwordless user should be available on every hypervisor host which will be used by the script to connect and run the `virsh` specific operations.

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

The CDROM is emulated as an IDE device. IDE controllers in QEMU have **no hotplug support** — all slots must be defined at VM creation time with SATA mode. If the VM was provisioned without a CDROM device in its XML in default cases, live attach will fail with:

```text
error: Operation not supported: cdrom/floppy device hotplug isn't supported
```

To ensure a CDROM slot is present from provisioning, set the following property on the Glance image before booting the VM:

```bash
openstack image set <IMAGE_UUID> --property hw_cdrom_bus=scsi --property hw_disk_bus=virtio  --property hw_scsi_model==virtio-scsi
```

> **Note:**
> -  `--property hw_machine_type=pc-i440fx` is not required as nova will automatically pick it automatically if no machine type defined.
> - cdrom bus as `SATA` sometime may not get emulated properly with default `i440fx` machine type. hence `SCSI `mode is recommended for cdrom

This causes Nova to include an empty SCSI CDROM device in the domain XML at boot, giving libvirt a slot to target at hotplug time. Without it, the only option is cold attach (`--config` without `--live`, requiring a reboot).


#### q35 — recommended for new VM deployments

q35 uses a PCIe bus with an ICH9 chipset. The CDROM is backed by a SATA controller (`ich9-ahci`), which **does support hotplug** at the controller level. This removes the architectural blocker present on i440fx.

Set the following properties on the Glance image to provision a q35 VM with a SATA CDROM slot:

```bash
openstack image set <IMAGE_UUID> --property hw_machine_type=q35 --property hw_cdrom_bus=sata --property hw_disk_bus=virtio  --property hw_scsi_model==virtio-scsi
```

The `hw_cdrom_bus=sata` property ensures the CDROM device is attached to the ICH9 SATA controller rather than falling back to IDE. Without it, Nova may still place the CDROM on an IDE bus even on q35, which reintroduces the hotplug limitation.

Alternatively, set these on a flavor to apply across all VMs using it:

```bash
openstack flavor set <FLAVOR> \
  --property hw:machine_type=q35 \
  --property hw:cdrom_bus=sata
```

> **Note:** Machine type is baked in at VM creation. Existing i440fx VMs cannot be converted to q35 in-place — a rebuild is required. For existing VMs without a CDROM slot, the recommended way would be to rebuild the VM with the required image properties set on the boot volume resource and use it to clone/snapshot for rebuilding.

#### Verification:
Once the ISO is attached as CDROM device successfully from inside the respective hypervisor, the followin virsh command would display iso in the list of block devices:
```
virsh domblklist ec580a0d-e6c8-42d6-a715-ca3dd781ea64 --details
 Type   Device   Target   Source
--------------------------------------------------------------------------------------------------------------------------------
 file   disk     vda      /opt/pf9/data/state/mnt/156e7d5a1fe842923e550061ad63ff74/volume-9b6e6076-e965-4bfa-a945-36c9e91b1d02
 file   cdrom    sdm      /var/opt/imagelibrary/data/glance/bc3c1a56-ba3e-41f8-8a06-f29abf4b129e
```

#### Example outputs:
- With VM name  as input:
```
./attach-deatch-cdrom-v3.sh --action attach --vm-name u24-test-3-i440fx  --image-uuid bc3c1a56-ba3e-41f8-8a06-f29abf4b129e --user ubuntu --tenant service
Resolving instance by name 'u24-test-3-i440fx' ...
Instance:   u24-test-3-i440fx (ec580a0d-e6c8-42d6-a715-ca3dd781ea64)
Resolving hypervisor for instance ec580a0d-e6c8-42d6-a715-ca3dd781ea64 ...
  Hypervisor hostname: sa-04
  Hypervisor IP:       10.96.11.132
Hypervisor: sa-04 (10.96.11.132)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor 10.96.11.132 is reachable via ICMP.
  [OK] SSH to ubuntu@10.96.11.132 succeeded.
  [OK] Image bc3c1a56-ba3e-41f8-8a06-f29abf4b129e status: active
  All pre-checks passed.

Domain:     ec580a0d-e6c8-42d6-a715-ca3dd781ea64

Attaching /var/opt/imagelibrary/data/glance/bc3c1a56-ba3e-41f8-8a06-f29abf4b129e to domain ec580a0d-e6c8-42d6-a715-ca3dd781ea64 as sdm ...
Disk attached successfully

Attached successfully.
  INSTANCE=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  GLANCE_IMAGE=bc3c1a56-ba3e-41f8-8a06-f29abf4b129e
  DOMAIN=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  DEVICE=/dev/sdm
  ISO=/var/opt/imagelibrary/data/glance/bc3c1a56-ba3e-41f8-8a06-f29abf4b129e

Done. 1 ISO(s) attached to ec580a0d-e6c8-42d6-a715-ca3dd781ea64.
```

- Detaching cdrom during runtime:
```
./attach-deatch-cdrom.sh --action detach --vm-ip 10.96.7.1  --user ubuntu
Resolving instance for IP 10.96.7.1 ...
Instance:   u24-test-3-i440fx (ec580a0d-e6c8-42d6-a715-ca3dd781ea64)
Resolving hypervisor for instance ec580a0d-e6c8-42d6-a715-ca3dd781ea64 ...
  Hypervisor hostname: sa-04
  Hypervisor IP:       10.96.11.132
Hypervisor: sa-04 (10.96.11.132)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor 10.96.11.132 is reachable via ICMP.
  [OK] SSH to ubuntu@10.96.11.132 succeeded.
  All pre-checks passed.

Domain:     ec580a0d-e6c8-42d6-a715-ca3dd781ea64

Detaching sdm (cdrom) from domain ec580a0d-e6c8-42d6-a715-ca3dd781ea64 ...
Disk detached successfully

Detached successfully.
  INSTANCE=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  DOMAIN=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  DEVICE=/dev/sdm
  NOTE: Glance image on NFS is unaffected.

Done. 1 ISO(s) detached from ec580a0d-e6c8-42d6-a715-ca3dd781ea64.
```

- If there are multiple VM association found for a specific ip address or name, the script will provide the list of VM and wait for user to provide the input to further proceed:
  
```
./attach-deatch-cdrom-v3.sh --action attach --vm-ip 10.96.7.1  --image-uuid bc3c1a56-ba3e-41f8-8a06-f29abf4b129e --user ubuntu --tenant service
Resolving instance for IP 10.96.7.1 (tenant: service) ...
Multiple instances match IP '10.96.7.1':
  1) ec580a0d-e6c8-42d6-a715-ca3dd781ea64  u24-test-3-i440fx
  2) 7e0aaec9-318a-4413-945e-81a7611eb983  u24-test-1-q35
  3) fd016a6a-133c-451c-b2c8-312d5a4676d3  cirros-test
  4) 8cbf156b-d20f-4258-9a39-1f6ca9d75425  win2k25-NLB-server-1
Select instance [1-4]: 1
Instance:   u24-test-3-i440fx (ec580a0d-e6c8-42d6-a715-ca3dd781ea64)
Resolving hypervisor for instance ec580a0d-e6c8-42d6-a715-ca3dd781ea64 ...
  Hypervisor hostname: sa-04
  Hypervisor IP:       10.96.11.132
Hypervisor: sa-04 (10.96.11.132)

==> Running pre-checks ...
  [OK] VM state: ACTIVE
  [OK] Hypervisor 10.96.11.132 is reachable via ICMP.
  [OK] SSH to ubuntu@10.96.11.132 succeeded.
  [OK] Image bc3c1a56-ba3e-41f8-8a06-f29abf4b129e status: active
  All pre-checks passed.

Domain:     ec580a0d-e6c8-42d6-a715-ca3dd781ea64

Attaching /var/opt/imagelibrary/data/glance/bc3c1a56-ba3e-41f8-8a06-f29abf4b129e to domain ec580a0d-e6c8-42d6-a715-ca3dd781ea64 as sdm ...
Disk attached successfully

Attached successfully.
  INSTANCE=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  GLANCE_IMAGE=bc3c1a56-ba3e-41f8-8a06-f29abf4b129e
  DOMAIN=ec580a0d-e6c8-42d6-a715-ca3dd781ea64
  DEVICE=/dev/sdm
  ISO=/var/opt/imagelibrary/data/glance/bc3c1a56-ba3e-41f8-8a06-f29abf4b129e

Done. 1 ISO(s) attached to ec580a0d-e6c8-42d6-a715-ca3dd781ea64.
```
