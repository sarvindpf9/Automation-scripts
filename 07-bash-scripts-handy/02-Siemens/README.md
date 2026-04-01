# 02-Siemens — OpenStack PCD Automation Scripts

Scripts used for managing OpenStack (PCD) VMs in the Siemens environment.

---

## `reboot-pcd-vms.sh` — Reboot OpenStack VMs by name

Resolves one or more VM names to UUIDs across all tenants/projects and reboots them sequentially. Requires admin-scoped OpenStack credentials.

**Usage**

```bash
./reboot-pcd-vms.sh [OPTIONS] <vm-name> [vm-name ...]
```

| Option | Description |
|---|---|
| `--hard` | Hard (power-cycle) reboot. Default is soft. |
| `--wait` | Wait for each VM to return to `ACTIVE` before moving to the next. |
| `--timeout N` | Max seconds to wait per VM when `--wait` is used (default: 90). |

**Examples**

```bash
# Soft reboot a single VM
./reboot-pcd-vms.sh my-vm-01

# Reboot multiple VMs
./reboot-pcd-vms.sh vm-a vm-b vm-c

# Hard reboot with active polling, 3-minute cap
./reboot-pcd-vms.sh --hard --wait --timeout 180 vm-prod-01 vm-prod-02
```

**What it does**

1. Resolves all VM names to UUIDs via `openstack server list --all-projects` before issuing any reboot — fails early if any name is ambiguous or not found.
2. Looks up the tenant/project name for each VM and includes it in all output.
3. Issues reboot commands one by one.
4. With `--wait`, polls VM state and exits the wait loop as soon as `ACTIVE` is detected. Handles transient states (`REBOOT`, `HARD_REBOOT`, `SHUTOFF`) and logs state transitions. On unrecoverable states (`ERROR`, `DELETED`) it logs and continues to the next VM rather than aborting.
5. Prints a pre- and post-reboot status block per VM, followed by a summary table.

**Requirements**

- `openstack` CLI configured with admin-scoped credentials (`OS_*` environment variables or `clouds.yaml`)
- Admin role required for `--all-projects` cross-tenant lookup
