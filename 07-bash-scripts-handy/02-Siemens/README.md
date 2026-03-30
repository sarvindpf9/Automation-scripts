# 02-Siemens — OpenStack PCD & KVM Automation Scripts

Scripts used for managing and auditing OpenStack (PCD) VMs and KVM compute hosts in the Siemens environment.

---

## Scripts

### `reboot-pcd-vms.sh` — Reboot OpenStack VMs by name

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

---

### `kvm-tuning-check-v1.sh` — KVM/Nova compute tuning audit (comprehensive)

Full audit of KVM and Nova compute host tuning state on Ubuntu 22.04. Covers kernel variant, CPU governor, CPU isolation, memory settings, storage I/O schedulers, network stack, kernel scheduler tunables, libvirt/QEMU/Nova service config, and lowlatency-specific risk checks.

**Usage**

```bash
# Run as root, output to console
sudo ./kvm-tuning-check-v1.sh

# Capture to a log file as well
sudo ./kvm-tuning-check-v1.sh /var/log/kvm-audit.log
```

**Checks performed**

| Section | What is checked |
|---|---|
| 1. Kernel variant | `linux-lowlatency` vs generic, HZ=1000, `CONFIG_PREEMPT` |
| 2. CPU governor | `performance` on all cores, EPP setting, `amd_pstate` |
| 3. CPU isolation | `isolcpus`, `nohz_full`, `rcu_nocbs`, `skew_tick`, cgroup CPU weight |
| 4. Memory | `vm.overcommit_memory`, swappiness, THP mode/defrag, hugepages, KSM |
| 5. Storage I/O | Per-device scheduler (`none`/`mq-deadline`/`bfq`), `fs.aio_max_nr` |
| 6. Network stack | Socket buffers, BBR congestion control, `fq` qdisc, irqbalance |
| 7. Scheduler | `sched_min_granularity_ns`, `sched_migration_cost_ns`, watchdog |
| 8. Services | `libvirtd`, `nova-compute`, `qemu.conf`, `nova.conf` parameters |
| 9. Lowlatency risks | DKMS modules, OVS-DPDK conflict, mixed fleet, thermald conflict |
| 10. GRUB cmdline | Snapshot of all kernel boot parameters |

Output uses colour-coded `[OK]` / `[WARN]` / `[FAIL]` markers with a summary count at the end.

---

### `kvm-tuning-check-v2.sh` — KVM tuning quick check (condensed)

Faster, more concise variant of the audit script. Covers the same areas in a compact format suited for quick spot-checks or regular cron runs.

**Usage**

```bash
sudo ./kvm-tuning-check-v2.sh
```

**Sections**

| Section | What is checked |
|---|---|
| A. GRUB cmdline | Key boot parameters (`preempt`, `isolcpus`, `nohz_full`, `rcu_nocbs`, etc.) |
| B. CPU governor | Scaling governor, EPP, `thermald`/`power-profiles-daemon` conflicts |
| C. Sysctl | Full set of memory, network, scheduler, and watchdog tunables |
| D. I/O scheduler | Per-device scheduler and `read_ahead_kb` |
| E. THP & KSM | THP mode/defrag, static hugepages, KSM state |
| F. cgroup priority | `machine.slice` and `system.slice` `CPUWeight`, drop-in persistence |
| G. nova.conf | `virt_type`, `cpu_mode`, `hw_machine_type`, queue sizes |
| H. qemu.conf | `set_process_name`, `max_processes`, `max_files` |
| I. IRQ affinity | `irqbalance` state vs `isolcpus`, `IRQBALANCE_BANNED_CPUS`, `vhost_net` |

**v1 vs v2 — when to use which**

| | v1 | v2 |
|---|---|---|
| Detail level | Deep — explains expected values inline | Concise — pass/warn/fail only |
| Log file support | Yes (`$1` argument) | No |
| Lowlatency risk checks | Yes (DKMS, OVS-DPDK, fleet check) | No |
| Best for | Initial audit / incident investigation | Routine checks / quick validation |

---

## Prerequisites

| Script | Requires |
|---|---|
| `reboot-pcd-vms.sh` | `openstack` CLI, admin-scoped credentials |
| `kvm-tuning-check-v1.sh` | Root on compute node, Ubuntu 22.04 |
| `kvm-tuning-check-v2.sh` | Root on compute node, Ubuntu 22.04 |
