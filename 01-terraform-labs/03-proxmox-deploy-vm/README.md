# Proxmox VM Automation with OpenTofu

Deploys Ubuntu 24 VMs on Proxmox VE by cloning a template, configuring them via cloud-init snippets, and generating an Ansible inventory. Supports multiple NICs, bridge-level VLAN tags, and VLAN sub-interfaces per NIC.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
  - [Connection Variables](#connection-variables)
  - [Template and Storage Variables](#template-and-storage-variables)
  - [VM Map (`vms`)](#vm-map-vms)
    - [Multiple NICs](#multiple-nics)
    - [Trunk NIC (No IP, VLAN Sub-interfaces Only)](#trunk-nic-no-ip-vlan-sub-interfaces-only)
    - [VLAN Sub-interfaces](#vlan-sub-interfaces)
    - [Full Two-NIC Example](#full-two-nic-example-from-proxmoxvmdeploytfvars)
- [Outputs](#outputs)
- [Generated Ansible Inventory](#generated-ansible-inventory)
- [How It Works](#how-it-works)
- [Gotchas](#gotchas)
  - [Template Requirements](#template-requirements)
  - [Snippet Datastore](#snippet-datastore)
  - [Interface Naming](#interface-naming)
  - [Disk Size](#disk-size)
  - [Default Route and Primary NIC](#default-route-and-primary-nic)
  - [Credentials and Security](#credentials-and-security)
  - [lifecycle { ignore_changes }](#lifecycle--ignore_changes-)
- [File Structure](#file-structure)

## Prerequisites

- OpenTofu >= 1.0 (or Terraform >= 1.3 — required for `optional()` in object type constraints)
- Proxmox VE node with:
  - An Ubuntu 24 template VM (cloud-init enabled, no QEMU guest agent required)
  - A datastore with **Snippets** content type enabled (default: `local`)
  - A datastore for VM disk storage (default: `local-1TB`)
- SSH public key for VM access
- Proxmox API token with sufficient privileges (VM creation, file upload, config update)

## Quick Start

```bash
# 1. Initialize providers
tofu init

# 2. Copy and edit the tfvars file
cp proxmoxVMDeploy.tfvars my.tfvars

# 3. Plan
tofu plan -var-file=my.tfvars

# 4. Apply
tofu apply -var-file=my.tfvars
```

After apply, `inventory.yml` is written to the module root for use with Ansible.

## Configuration Reference

### Connection Variables

| Variable | Description | Default |
|---|---|---|
| `proxmox_url` | Proxmox API URL, e.g. `https://192.168.1.82:8006` | required |
| `proxmox_api_token` | API token in `USER@REALM!TOKEN_ID=SECRET` format | required |
| `proxmox_insecure` | Skip TLS certificate verification | `true` |
| `proxmox_ssh_username` | SSH user for snippet file uploads | `root` |
| `proxmox_ssh_password` | SSH password for snippet file uploads | required |
| `proxmox_node` | Proxmox node name (e.g. `homelab-pve`) | required |

### Template and Storage Variables

| Variable | Description | Default |
|---|---|---|
| `template_vm_id` | VM ID of the Ubuntu 24 clone template | `9000` |
| `datastore_id` | Datastore for VM disk storage | `local-1TB` |
| `snippet_datastore_id` | Datastore for cloud-init snippets (must have Snippets content type) | `local` |
| `ssh_public_key_path` | Local path to SSH public key injected into VMs | `~/.ssh/id_rsa.pub` |

### VM Map (`vms`)

Each key in the `vms` map defines one VM. Validation rules are enforced at plan time:

- `vm_id`: 100–999999
- `cores`: 1–80
- `memory_mb`: 512–32768

```hcl
vms = {
  "vm1" = {
    vm_name      = "my-server"       # VM display name in Proxmox
    vm_id        = 1000              # Proxmox VM ID (100–999999)
    memory_mb    = 4096              # RAM in MB (512–32768)
    cores        = 4                 # vCPU cores (1–80)
    sockets      = 1                 # CPU sockets
    disk_size_gb = 50                # Disk size in GB (must be >= template disk size)

    network_interfaces = [
      {
        bridge       = "vmbr0"       # Proxmox Linux bridge
        vlan_id      = 100           # VLAN tag applied to the bridge port (omit for untagged)
        ip           = "10.0.1.10/24"
        gw           = "10.0.1.1"    # Optional — set on the NIC that carries the default route
        dns          = ["8.8.8.8"]   # Optional
        vlan_devices = []            # Optional — see VLAN sub-interfaces below
      }
    ]
  }
}
```

#### Multiple NICs

Add additional entries to `network_interfaces`. NICs are assigned Proxmox PCI slots in list order. The first NIC (`[0]`) is used as the primary IP in outputs and the Ansible inventory.

```hcl
network_interfaces = [
  {
    bridge  = "vmbr0"
    vlan_id = 100
    ip      = "10.0.1.10/24"
    gw      = "10.0.1.1"
    dns     = ["8.8.8.8", "8.8.4.4"]
    vlan_devices = []
  },
  {
    bridge  = "vmbr1"
    vlan_id = 200
    ip      = "10.0.2.10/24"
    # gw omitted — no default route on secondary NIC
    vlan_devices = []
  }
]
```

#### Trunk NIC (No IP, VLAN Sub-interfaces Only)

A NIC can be configured as a trunk port: no bridge-level VLAN tag, no IP on the interface itself. All traffic is carried by VLAN sub-interfaces defined in `vlan_devices`. Omit both `vlan_id` and `ip`:

```hcl
{
  bridge  = "vmbr0"
  # vlan_id omitted = no bridge-level VLAN tag (trunk/access as-is)
  # ip omitted      = no address on the interface itself
  vlan_devices = [
    { id = 300, ip = "192.168.30.10/24", gw = "192.168.30.1" },
    { id = 400, ip = "192.168.40.10/24" }
  ]
}
```

The netplan config for a trunk NIC uses `dhcp4: false` (activates the link layer without assigning an IP), `dhcp6: false` (suppresses IPv6 link-local), and `optional: true` (prevents `systemd-networkd-wait-online` from stalling boot waiting for the interface to become routable).

#### VLAN Sub-interfaces

Each NIC can carry VLAN sub-interfaces (`eth0.300`, `eth0.400`, etc.) configured via `vlan_devices`:

```hcl
network_interfaces = [
  {
    bridge  = "vyosvlanbr"
    vlan_id = 500
    ip      = "172.17.0.10/20"
    gw      = "172.17.0.1"
    dns     = ["8.8.8.8"]
    vlan_devices = [
      { id = 300, ip = "192.168.30.10/24", gw = "192.168.30.1" },
      { id = 400, ip = "192.168.40.10/24" }
    ]
  }
]
```

#### Full Two-NIC Example (from `proxmoxVMDeploy.tfvars`)

NIC 0 with a bridge-level VLAN tag and a default route; NIC 1 as a trunk with VLAN sub-interfaces only:

```hcl
network_interfaces = [
  # NIC 0 — VLAN 500 tagged at bridge level, default route to external network
  {
    bridge       = "vyosvlanbr"
    vlan_id      = 500
    ip           = "172.17.0.111/20"
    gw           = "172.17.0.1"
    dns          = ["8.8.8.8", "8.8.4.4"]
    vlan_devices = []
  },
  # NIC 1 — untagged trunk port, no IP; sub-interfaces carry the addresses
  {
    bridge  = "vmbr0"
    vlan_devices = [
      { id = 300, ip = "192.168.30.10/24", gw = "192.168.30.1" },
      { id = 400, ip = "192.168.40.10/24" }
    ]
  }
]
```

## Outputs

| Output | Description |
|---|---|
| `vm_ips` | Map of `vm_name => primary_ip` |
| `vm_details` | Map of `vm_name => { vm_id, primary_ip, network_interfaces }` |
| `ansible_inventory_path` | Path to the generated `inventory.yml` |
| `terraform_outputs_summary` | Summary: total VMs, names, IPs, inventory path |

## Generated Ansible Inventory

After apply, `inventory.yml` is written to the module root. It groups all deployed VMs under `proxmox_vms`, uses the `ubuntu` user with SSH key auth, and includes group-level variables for NTP, DNS, and privilege escalation:

```yaml
all:
  children:
    proxmox_vms:
      hosts:
        my-server:
          ansible_host: 10.0.1.10
          ansible_user: ubuntu
          ansible_ssh_private_key_file: "~/.ssh/homelab-key"
          ansible_python_interpreter: /usr/bin/python3
      vars:
        ansible_become_method: sudo
        ansible_become_user: root
        ntp_timezone: UTC
        ntp_servers: [0.ubuntu.pool.ntp.org, ...]
        dns_nameservers: [1.1.1.1, 8.8.8.8, 8.8.4.4]
```

The SSH private key path is hardcoded to `~/.ssh/homelab-key` in [templates/host_inventory.tftpl](templates/host_inventory.tftpl) — update it if your key is elsewhere.

## How It Works

1. **Cloud-init snippets** — Two snippets are uploaded to Proxmox per VM:
   - `user-data`: creates the `ubuntu` user, injects the SSH key, writes and runs `apply-netplan.sh`
   - `network-data`: writes a netplan config with placeholder interface names (`eth0`, `eth1`, ...)

2. **Interface name resolution** — Proxmox VMs use kernel-assigned names (`ens18`, `ens19`, ...) not `eth0/eth1`. On first boot, `apply-netplan.sh` discovers virtio interfaces from sysfs sorted by virtio device number (`virtio0`, `virtio1`, ...) — not by interface name — to guarantee the array index matches the Proxmox NIC slot order. A single ERE `sed` pass then replaces all `ethN` placeholder references in `/etc/netplan/50-cloud-init.yaml` (interface keys, `link:` entries, and VLAN dot-names) before calling `netplan apply`.

3. **Trunk port activation** — For NICs with no IP, the generated netplan sets `dhcp4: false` to bring up the link layer, `dhcp6: false` to suppress IPv6 link-local, and `optional: true` to prevent boot stalls. VLAN sub-interfaces are defined under the `vlans:` stanza and reference the trunk interface by its real kernel name after the sed replacement.

4. **Cloud-init drive cleanup** — After the VM starts, a `null_resource` calls the Proxmox API via curl to detach the `ide2` cloud-init drive (it has served its purpose).

## Gotchas

### Template Requirements

- The template must have cloud-init enabled and the `ide2` drive configured as the cloud-init source. The module clones the template and re-configures cloud-init via snippets.
- The template does **not** need a QEMU guest agent installed. The provider is configured with `agent { enabled = false }` and `timeout_start_vm = 60`.

### Snippet Datastore

- The datastore used for snippets (`snippet_datastore_id`, default `local`) must have the **Snippets** content type enabled in Proxmox (Datacenter → Storage → Edit → Content). If it does not, the `proxmox_virtual_environment_file` resource will fail at apply time.

### Interface Naming

- Cloud-init network config is written with placeholder names `eth0`, `eth1`, etc. `apply-netplan.sh` replaces these at first boot. If the script fails (check `/var/log/cloud-init-output.log`), the VM will have no static IP.
- Interfaces are discovered in virtio PCI slot order (`virtio0`, `virtio1`, ...). This order matches the `network_interfaces` list order in your tfvars.

### Disk Size

- `disk_size_gb` (default: `50`) is passed directly to the Proxmox disk block. It must be **greater than or equal to** the template's disk size — Proxmox will reject a shrink request at apply time. To use the template's disk size as-is, set `disk_size_gb` to match it.

### Default Route and Primary NIC

- Only set `gw` on one NIC — the one that should carry the default route. Setting `gw` on multiple NICs will generate multiple `routes: to: default` entries in netplan and may cause unpredictable routing.
- The first NIC (`network_interfaces[0]`) is used as `primary_ip` in outputs and the Ansible inventory. If NIC 0 has no static IP (trunk port), `primary_ip` will be an empty string.

### Credentials and Security

- `proxmoxVMDeploy.tfvars` contains plaintext API tokens and SSH passwords. Do not commit it to version control — add it to `.gitignore` or use environment variables / a secrets manager.
- The cloud-init `user-data` snippet sets the `ubuntu` account password to the literal string `password` via `chpasswd`. This is a fallback for console access. SSH key auth is the intended access method; consider disabling password auth in `/etc/ssh/sshd_config` post-deploy.
- A `random_password` resource generates a 20-character password per VM and stores it in Terraform state. It is not currently wired into cloud-init (the `chpasswd` value is still hardcoded). Treat your Terraform state file as sensitive.

### `lifecycle { ignore_changes }`

- `clone` and `initialization` are in `ignore_changes`. After initial deployment, changes to the template ID or cloud-init snippet content will not trigger a replacement. To reprovision, taint the VM resource (`tofu state rm` + re-apply) or destroy and re-apply.

## File Structure

```
01-opentofu/
├── provider.tf              # Provider config (bpg/proxmox ~> 0.66, random ~> 3.5, local ~> 2.4)
├── vars.tf                  # Root variable declarations (with validation rules)
├── local.tf                 # Local values (timestamp, vm_deployments map)
├── vm.tf                    # Module instantiation (one module call per VM)
├── outputs.tf               # Root outputs + Ansible inventory resource
├── proxmoxVMDeploy.tfvars   # Example variable values (do not commit)
├── templates/
│   └── host_inventory.tftpl # Ansible inventory template (update SSH key path here)
└── modules/
    └── proxmox-vm/
        ├── main.tf          # VM resource, cloud-init snippets, apply-netplan.sh, drive detach
        ├── vars.tf          # Module variable declarations
        └── outputs.tf       # Module outputs (vm_id, vm_name, primary_ip, network_interfaces)
```
