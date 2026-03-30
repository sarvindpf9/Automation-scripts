# 01-NTT — Bash Scripts

Scripts for OpenStack/PCD VM provisioning and KVM multipath diagnostics.

---

## Scripts

### `launch-VM-with-images.sh`

Provisions three Cinder volumes from Windows ISO and VirtIO driver ISO images, sets UEFI/q35 firmware properties on the target OS volume, and launches a Windows VM on OpenStack/PCD.

**Dependencies:** `openstack` CLI, sourced OpenStack credentials (`openrc` or environment variables)

**What it creates:**
| Volume | Source | Size | Purpose |
|--------|--------|------|---------|
| `windows-os-target-<suffix>` | blank | 20 GB | Boot disk for Windows installation |
| `windows-installation-<suffix>` | Windows ISO image | 10 GB | Windows installer CDROM |
| `virtio-driver-<suffix>` | VirtIO ISO image | 2 GB | VirtIO driver CDROM |

Volume names include a `<timestamp>-<PID>` suffix to prevent duplicate-name collisions on repeated runs.

**Firmware/hardware properties set on the OS volume:**
`hw_firmware_type=uefi`, `hw_machine_type=q35`, `hw_cdrom_bus=sata`, `hw_disk_bus=virtio`, `hw_scsi_model=virtio-scsi`, `os_secure_boot=required`, `os_type=windows`, `hw_video_model=qxl`, `hw_boot_menu=true`

**Usage:**

```bash
# Attach VM via network name or UUID
./launch-VM-with-images.sh \
  --windows-iso <windows-iso-image-uuid> \
  --virtio-iso  <virtio-iso-image-uuid> \
  --network     <network-name-or-uuid> \
  --az          <availability-zone> \
  --vm-name     <vm-name>

# Attach VM via a pre-created port UUID
./launch-VM-with-images.sh \
  --windows-iso <windows-iso-image-uuid> \
  --virtio-iso  <virtio-iso-image-uuid> \
  --port        <port-uuid> \
  --az          <availability-zone> \
  --vm-name     <vm-name>

# Specify a Cinder volume type for all three volumes
./launch-VM-with-images.sh \
  --windows-iso <windows-iso-image-uuid> \
  --virtio-iso  <virtio-iso-image-uuid> \
  --network     <network-name-or-uuid> \
  --az          <availability-zone> \
  --vm-name     <vm-name> \
  --volume-type <cinder-volume-type>
```

**Options:**

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--windows-iso UUID` | `-w` | Yes | UUID of the Windows ISO image in Glance |
| `--virtio-iso UUID` | `-v` | Yes | UUID of the VirtIO driver ISO image in Glance |
| `--az ZONE` | `-a` | Yes | Availability zone / PCD cluster name |
| `--vm-name NAME` | `-n` | Yes | Name for the new VM |
| `--network UUID\|NAME` | | One of these | Attach VM to this network |
| `--port UUID` | | One of these | Attach VM to this pre-created port |
| `--volume-type TYPE` | `-t` | No | Cinder volume type applied to all three volumes |
| `--help` | `-h` | No | Show usage and exit |

**Example:**

```bash
# Minimal — no volume type (backend default)
./launch-VM-with-images.sh \
  -w e1a2b3c4-0000-0000-0000-win2022iso \
  -v f5d6e7f8-0000-0000-0000-virtiodrivers \
  --network tenant-net-prod \
  -a nova-pcd-cluster-01 \
  -n win2022-install-01

# With explicit volume type
./launch-VM-with-images.sh \
  -w e1a2b3c4-0000-0000-0000-win2022iso \
  -v f5d6e7f8-0000-0000-0000-virtiodrivers \
  --network tenant-net-prod \
  -a nova-pcd-cluster-01 \
  -n win2022-install-01 \
  -t ceph-ssd
```

**Volume registry log:**

After each run, the names and UUIDs of the three created volumes are appended to `volume-registry.log` in the same directory. Each line records the timestamp, VM name, volume role, volume name, and UUID:

```text
2026-03-30T14:32:01  vm=win2022-install-01            role=os-target   name=windows-os-target-20260330143201-12345       uuid=aaaa-...
2026-03-30T14:32:01  vm=win2022-install-01            role=win-iso     name=windows-installation-20260330143201-12345    uuid=bbbb-...
2026-03-30T14:32:01  vm=win2022-install-01            role=virtio-iso  name=virtio-driver-20260330143201-12345           uuid=cccc-...
```

This file is append-only — repeated runs accumulate entries, making it easy to trace which volumes belong to which VM.

**Monitor VM status after launch:**

```bash
openstack server show <vm-name> --insecure
```

---

### `vm-multipath-check.sh`

Iterates over **all running VMs** on the local KVM hypervisor, lists their block devices, extracts any `dm-*` (device-mapper) disk sources, and shows the corresponding `multipath -ll` entry for each.

Use this to verify that VM disks are backed by properly configured multipath devices.

**Dependencies:** `virsh`, `multipath`, `awk`, `grep`, `sed` — must run on the KVM hypervisor host as root (or with sufficient privileges).

**Usage:**

```bash
sudo ./vm-multipath-check.sh
```

**Output per VM:**
1. `virsh domblklist --details` — all attached block devices and their source paths
2. For each `dm-*` source found: 5 lines of `multipath -ll` context showing path group and path state

**Example output:**

```
==================================================================
VM: win2022-prod-01
-- domblklist --details --
Type   Device   Driver  Source
disk   vda      -       /dev/dm-3
...
-- multipath context for dm devices --
------------------
>>> dm-3
mpatha (360000000000000001) dm-3 VENDOR,PRODUCT
  size=20G features='1 queue_if_no_path' hwhandler='0' wp=rw
  `-+- policy='service-time 0' prio=1 status=active
    |- 1:0:0:1 sdb 8:16 active ready running
    |- 2:0:0:1 sdc 8:32 active ready running
```

---

### `vm-mpath-check-uuid.sh`

Same multipath diagnostic as `vm-multipath-check.sh` but targets a **single VM** specified by UUID or name, rather than iterating all running VMs.

**Dependencies:** `virsh`, `multipath`, `awk`, `grep`, `sed` — must run on the KVM hypervisor host as root.

**Usage:**

```bash
sudo ./vm-mpath-check-uuid.sh <vm-uuid-or-name>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `<vm-uuid-or-name>` | The libvirt UUID or domain name of the target VM |

**Example:**

```bash
# By UUID
sudo ./vm-mpath-check-uuid.sh 4a5b6c7d-1234-5678-abcd-ef0123456789

# By VM name
sudo ./vm-mpath-check-uuid.sh win2022-prod-01
```

Returns exit code `0` if no `dm-*` devices are found (not an error — VM may use other storage backends).

---

## Prerequisites Summary

| Script | Run as | Host type | Key binaries |
|--------|--------|-----------|--------------|
| `launch-VM-with-images.sh` | any user with OpenStack credentials | jump host / workstation | `openstack` |
| `vm-multipath-check.sh` | root | KVM hypervisor | `virsh`, `multipath` |
| `vm-mpath-check-uuid.sh` | root | KVM hypervisor | `virsh`, `multipath` |
