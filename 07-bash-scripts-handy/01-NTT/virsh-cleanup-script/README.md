# virsh-cleanup-script

Inspect and optionally clean up dm-mpath block devices attached to a stuck or abandoned libvirt VM on a KVM hypervisor, then forcibly destroy the VM.

---

## `virsh-DM-cleanup.sh`

Resolves all `/dev/dm-*` devices attached to a VM, prints their multipath path status, and — when `--force-cleanup` is passed — sets `fail_if_no_path` on each dm device and prompts to `virsh destroy` the VM.

**Dependencies:**
- `virsh` — querying VM block device list and issuing destroy
- `dmsetup` — resolving dm map names (`dmsetup info`) and sending queue policy messages (`dmsetup message`)
- `multipath` — displaying path status per dm device (`multipath -ll`)
- Must be run as root or a user with sudo-equivalent access to libvirt and dm targets

**What it does:**

1. Parses `virsh domblklist --details` to collect all `/dev/dm-*` devices attached to the VM
2. For each dm device, resolves the multipath map name via `dmsetup info` and prints `multipath -ll` output
3. (`--force-cleanup` only) Sends `fail_if_no_path` to each dm device via `dmsetup message`, changing the queue policy so in-flight I/O fails immediately rather than queuing indefinitely
4. (`--force-cleanup` only) Prompts for confirmation, then runs `virsh destroy` on the VM

### Usage

```bash
# Inspect only: print attached dm devices and their multipath status
./virsh-DM-cleanup.sh <vm-uuid>

# Inspect + apply fail_if_no_path + prompt to virsh destroy
./virsh-DM-cleanup.sh <vm-uuid> --force-cleanup
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `<vm-uuid>` | Yes | Libvirt domain UUID of the target VM (Nova instance UUID on OpenStack) |
| `--force-cleanup` | No | Apply `dmsetup message fail_if_no_path` on all dm devices and prompt to `virsh destroy` the VM |
| `--help`, `-h` | No | Show usage and exit |

### Examples

```bash
# Safe inspection — no changes made to the VM or its devices
./virsh-DM-cleanup.sh ec580a0d-e6c8-42d6-a715-ca3dd781ea64

# Full cleanup: unblock queued I/O on dm devices, then destroy the VM
./virsh-DM-cleanup.sh ec580a0d-e6c8-42d6-a715-ca3dd781ea64 --force-cleanup
```

### Why fail_if_no_path

When storage paths are lost (Ceph RBD I/O hang, FC/iSCSI path failure), the dm-mpath device queues I/O indefinitely by default. `virsh destroy` can block waiting for that I/O to drain. Setting `fail_if_no_path` forces the queue policy to immediately return errors to the guest, which unblocks the destroy.

This is a destructive change to the dm device's queue policy and is only appropriate when the VM is being torn down. Do not apply it to running VMs that are expected to recover path connectivity.

### Pre-check behaviour

| Check | Applies to |
|-------|-----------|
| `virsh`, `dmsetup`, `multipath` binaries present | inspect + execute |
| VM UUID resolves via `virsh domblklist` | inspect + execute |
| At least one `/dev/dm-*` device found for the VM | inspect + execute |
| dm path is a valid block device before dmsetup operations | execute only |

### Example outputs

- Inspect only:

```
Block devices for VM: ec580a0d-e6c8-42d6-a715-ca3dd781ea64
──────────────────────────────────────────────────
  /dev/dm-3
  /dev/dm-7

Multipath status (VM disks only)
──────────────────────────────────────────────────

  [/dev/dm-3  →  mpatha]
mpatha (360000000000000001) dm-3 VENDOR,PRODUCT
size=50G features='1 queue_if_no_path' hwhandler='0' wp=rw
`-+- policy='service-time 0' prio=1 status=active
  |- 2:0:0:1 sdb 8:16  active ready running
  `- 3:0:0:1 sdc 8:32  active ready running

  [/dev/dm-7  →  mpathb]
mpathb (360000000000000002) dm-7 VENDOR,PRODUCT
size=100G features='1 queue_if_no_path' hwhandler='0' wp=rw
`-+- policy='service-time 0' prio=1 status=active
  |- 2:0:0:2 sdd 8:48  active ready running
  `- 3:0:0:2 sde 8:64  active ready running

  Run with --force-cleanup to apply dmsetup fail_if_no_path and destroy the VM.
```

- With `--force-cleanup`:

```
Block devices for VM: ec580a0d-e6c8-42d6-a715-ca3dd781ea64
──────────────────────────────────────────────────
  /dev/dm-3
  /dev/dm-7

Multipath status (VM disks only)
──────────────────────────────────────────────────

  [/dev/dm-3  →  mpatha]
  ...

Setting fail_if_no_path on dm devices
──────────────────────────────────────────────────
  dmsetup message /dev/dm-3 0 fail_if_no_path
  OK    /dev/dm-3
  dmsetup message /dev/dm-7 0 fail_if_no_path
  OK    /dev/dm-7

──────────────────────────────────────────────────
Destroy VM 'ec580a0d-e6c8-42d6-a715-ca3dd781ea64' with virsh destroy? [yes/N]: yes
  VM 'ec580a0d-e6c8-42d6-a715-ca3dd781ea64' destroyed.
```
