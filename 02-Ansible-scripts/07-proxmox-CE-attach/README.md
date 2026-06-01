# 07-proxmox-CE-attach

End-to-end automation to create Proxmox VMs and attach them to a Platform9 PCD region as Compute Engine (CE) nodes.

## Overview

Three sequential phases, each a standalone playbook:

| Phase | Playbook | Target | What it does |
|-------|----------|--------|--------------|
| 1 | `01-create-vms.yml` | `proxmox_nodes` | Clones VMs from a cloud-init template, renders snippets, sizes disks, starts VMs |
| 2 | `02-commission-hosts.yml` | `ce_nodes` | Downloads `cloud-ctl`, runs `cloud-ctl prep-node` to onboard each host into PCD |
| 3 | `03-prepare-ce-vms.yml` | `ce_nodes` | Applies persistent netplan config, creates NFS mount points and fstab entries, sets hostname |

Run all phases in sequence with `site.yml`, or invoke each playbook independently.

## Prerequisites

- Ansible controller with Python ≥ 3.9
- Proxmox node reachable over SSH from the controller
- PCD region deployed and accessible
- Ubuntu cloud-init template registered on the Proxmox node
- NFS server provisioned for image library and ephemeral storage

### Python packages

```bash
pip install ansible-core>=2.14 proxmoxer>=2.0 requests>=2.31
```

### Ansible collections

```bash
ansible-galaxy collection install -r requirements.yml
```

## Configuration

All variables live in `group_vars/all.yml`. Fill in every `<PLACEHOLDER>` before running. Variables are grouped by phase:

### Phase 1 — Proxmox VM creation

| Variable | Description |
|----------|-------------|
| `proxmox_api_host` | Proxmox API hostname/IP |
| `proxmox_api_user` | API user with realm (e.g. `root@pam`) |
| `proxmox_api_password` | API password — use Vault |
| `proxmox_node` | Proxmox node name where VMs are created |
| `template_vm_id` / `template_vm_name` | Source cloud-init template |
| `datastore_id` | Storage for cloned disks |
| `vms` | Map of VMs to create (name, ID, CPU, RAM, disk, NICs) |

### Phase 2 — PCD commissioning

| Variable | Description |
|----------|-------------|
| `pcd_region_portal` | PCD management URL |
| `pcd_username` / `pcd_password` | PCD credentials — use Vault |
| `pcd_project_name` | OpenStack project (typically `service`) |
| `pcd_region_name` | PCD region name |
| `cloud_ctl_url` | Override to pin a specific `cloud-ctl` version |

### Phase 3 — CE node preparation

| Variable | Description |
|----------|-------------|
| `secondary_interface_name` | Data NIC — rendered with `dhcp4: false`, no addresses |
| `netplan_nameservers` | DNS servers for the management interface |
| `ce_fstab_entries` | NFS mounts for image library and ephemeral storage |
| `ce_hostname` | Optional hostname override (blank = keep cloud-init default) |

## Inventory

Edit `inventory.yaml` to add your Proxmox node under `proxmox_nodes` and each CE VM under `ce_nodes`. The `ansible_host` for each CE node must match the management IP set in the `vms` map.

## Usage

### Full workflow (all three phases)

```bash
ansible-playbook playbooks/site.yml
```

### Individual phases

```bash
# Phase 1 only — create VMs
ansible-playbook playbooks/01-create-vms.yml

# Phase 2 only — commission into PCD (VMs must already be running)
ansible-playbook playbooks/02-commission-hosts.yml

# Phase 3 only — netplan and NFS prep
ansible-playbook playbooks/03-prepare-ce-vms.yml
```

### Using Vault for secrets

```bash
ansible-playbook playbooks/site.yml --ask-vault-pass
# or with a vault file:
ansible-playbook playbooks/site.yml --vault-password-file ~/.vault_pass
```

## Directory layout

```
07-proxmox-CE-attach/
├── ansible.cfg
├── inventory.yaml
├── requirements.yml
├── group_vars/
│   └── all.yml                    # All variables for all three phases
├── playbooks/
│   ├── site.yml                   # Master — chains all three phases
│   ├── 01-create-vms.yml          # Phase 1: Proxmox VM creation
│   ├── 02-commission-hosts.yml    # Phase 2: cloud-ctl commissioning
│   └── 03-prepare-ce-vms.yml      # Phase 3: netplan, NFS, hostname
├── tasks/
│   ├── preflight.yml              # Validate Proxmox vars and VM map
│   ├── render-snippets.yml        # Render cloud-init snippets to Proxmox node
│   ├── clone-vms.yml              # Clone, configure, resize, start VMs
│   ├── cloud-ctl-download.yml     # Download cloud-ctl binary to CE node
│   └── commission-host.yml        # cloud-ctl config set + prep-node
└── templates/
    ├── network-data.yaml.j2       # cloud-init network config for each VM
    ├── proxmox-net.yml.j2         # Proxmox NIC map for proxmox_kvm module
    ├── user-data.yaml.j2          # cloud-init user/ssh config
    ├── vm-ip-list.yml.j2          # IP uniqueness check helper
    └── 50-cloud-init.yaml.j2      # Persistent netplan config (Phase 3)
```

## Idempotency notes

- **Phase 1**: VM cloning is skipped if the VM ID already exists on the node. Hardware config and cicustom are re-applied on every run via `update: true`.
- **Phase 2**: Commissioning is skipped if `/etc/pf9/host_id.conf` already exists on the target host.
- **Phase 3**: All tasks are idempotent — netplan is re-rendered only if the template changes; fstab entries use `lineinfile` with a regexp guard.
