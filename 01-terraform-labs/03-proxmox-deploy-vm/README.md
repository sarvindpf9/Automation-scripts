# Proxmox VM Automation with OpenTofu

OpenTofu templates for deploying Ubuntu 24 VMs on Proxmox VE by cloning a cloud-init template, uploading user-data/network-data snippets, starting the VM, detaching the `ide2` cloud-init drive after first boot, and generating an Ansible inventory.

> Sensitive data warning: the `proxmoxVMDeploy.tfvars` files are environment-specific and may contain Proxmox credentials, node names, datastore names, IP addresses, and SSH key paths. Treat `*.tfvars`, generated `inventory.yml`, and OpenTofu state as sensitive.

---

## Template Options

| Directory | API auth | IP mode | Use when |
| ---- | -------- | ------- | -------- |
| `01-templates-api-keys` | API token | Static or VLAN-only | You have a Proxmox API token and want non-password API auth. |
| `02-templates-generic` | Username/password | Static or VLAN-only | You want to authenticate to the Proxmox API with a normal Proxmox user/password. |
| `03-templates-dhcp` | Username/password | Static, DHCP, none, or VLAN-only | You need DHCP primary IP discovery through QEMU guest agent. |

All templates support multiple VMs through the `vms` map, multiple NICs, bridge-level VLAN tags, VLAN sub-interfaces, full clones from a Proxmox template VM, cloud-init snippets, and generated `inventory.yml`.

## Prerequisites

**Local workstation:**

- `tofu` — OpenTofu CLI.
- `curl` — used by cleanup and pre-check provisioners.
- `python3` — parses Proxmox API JSON responses in local provisioners.
- SSH reachability to the Proxmox node for snippet upload through the `bpg/proxmox` provider.

**Proxmox/template requirements:**

- `template_vm_id` must point to an existing Proxmox VM template.
- `datastore_id` must be valid for VM disks.
- `snippet_datastore_id` must support Proxmox `snippets` content.
- VM IDs in `vms[*].vm_id` must not already exist in the Proxmox cluster.
- For `03-templates-dhcp`, the guest image must have `qemu-guest-agent` installed and enabled.

## Common Run Flow

Run commands from exactly one template directory.

```bash
tofu init
tofu fmt -check -recursive
tofu validate
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Destroy VMs from the same directory and same variable file:

```bash
tofu destroy -var-file=proxmoxVMDeploy.tfvars
```

## `01-templates-api-keys`

API-token based template for static IP or VLAN-only VM definitions.

```bash
cd 01-terraform-labs/03-proxmox-deploy-vm/01-templates-api-keys
tofu init
tofu validate
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Required API auth variables:

```hcl
proxmox_url       = "https://<PROXMOX_HOST>:8006"
proxmox_api_token = "<USER>@<REALM>!<TOKEN_ID>=<TOKEN_SECRET>"
```

The provider uses `api_token`. The cloud-init drive cleanup uses the same token in the `PVEAPIToken` authorization header.

## `02-templates-generic`

Username/password based template for static IP or VLAN-only VM definitions.

```bash
cd 01-terraform-labs/03-proxmox-deploy-vm/02-templates-generic
tofu init
tofu validate
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Required API auth variables:

```hcl
proxmox_url          = "https://<PROXMOX_HOST>:8006"
proxmox_api_username = "<USER>@<REALM>"
proxmox_api_password = "<PROXMOX_PASSWORD>"
```

The provider uses `username` and `password`. The cloud-init drive cleanup logs in to `/api2/json/access/ticket`, then uses the returned `PVEAuthCookie` and `CSRFPreventionToken` for the `ide2` detach call.

## `03-templates-dhcp`

Username/password based template for DHCP-aware VM definitions. Use this variant when the primary NIC should receive its address from DHCP and the generated outputs/inventory must contain that DHCP address.

```bash
cd 01-terraform-labs/03-proxmox-deploy-vm/03-templates-dhcp
tofu init
tofu validate
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Required API auth variables:

```hcl
proxmox_url          = "https://<PROXMOX_HOST>:8006"
proxmox_api_username = "<USER>@<REALM>"
proxmox_api_password = "<PROXMOX_PASSWORD>"
```

DHCP-specific options:

```hcl
guest_agent_ip_initial_delay_seconds = 90
guest_agent_ip_max_wait_seconds      = 900
```

`guest_agent_ip_initial_delay_seconds` waits before querying QEMU guest agent. This is useful for templates that reset `machine-id` and force a first-boot reboot. `guest_agent_ip_max_wait_seconds` controls how long the module polls Proxmox for a non-loopback DHCP IPv4 address.

The DHCP module enables the QEMU guest agent flag on the VM, queries `/agent/network-get-interfaces`, ignores loopback/link-local/unspecified IPv4 addresses such as `127.0.0.1`, and writes the discovered primary IP into Terraform outputs and `inventory.yml`.

## Shared Variables

SSH credentials are used by the Proxmox provider for node-side snippet uploads and are separate from API authentication:

```hcl
proxmox_ssh_username = "<PROXMOX_NODE_SSH_USER>"
proxmox_ssh_password = "<PROXMOX_NODE_SSH_PASSWORD>"
```

Common VM/storage settings:

```hcl
proxmox_node         = "<PROXMOX_NODE_NAME>"
template_vm_id       = <TEMPLATE_VM_ID>
datastore_id         = "<VM_DISK_DATASTORE>"
snippet_datastore_id = "<SNIPPET_DATASTORE>"
ssh_public_key_path  = "~/.ssh/<PUBLIC_KEY>.pub"
```

Common VM object fields:

| Field | Required | Description |
| ---- | -------- | ----------- |
| `vm_name` | Yes | VM name created in Proxmox and used in outputs/inventory. |
| `vm_id` | Yes | Proxmox VM ID. Must be unique in the cluster. |
| `memory_mb` | Yes | Dedicated memory in MB. |
| `cores` | Yes | CPU cores per socket. |
| `sockets` | Yes | CPU socket count. |
| `disk_size_gb` | No | Disk size in GB; defaults to `50`. |
| `network_interfaces` | Yes | NIC list in Proxmox slot order. The first NIC is treated as primary. |

Network interface fields:

| Field | Required | Description |
| ---- | -------- | ----------- |
| `bridge` | Yes | Proxmox bridge for the NIC. |
| `vlan_id` | No | Bridge-level VLAN tag. Omit or set `null` for untagged. |
| `ip` | Static only | CIDR address for static primary/NIC configuration. |
| `gw` | No | Default route gateway for that NIC or VLAN sub-interface. |
| `dns` | No | DNS resolver list for that NIC. |
| `vlan_devices` | No | VLAN sub-interfaces created inside the guest. |
| `ip_mode` | `03-templates-dhcp` only | `static`, `dhcp`, or `none`; inferred as `static` when `ip` is set and omitted. |

Static primary NIC example:

```hcl
network_interfaces = [
  {
    bridge  = "<PROXMOX_BRIDGE>"
    vlan_id = <VLAN_ID>
    ip      = "<VM_IP_CIDR>"
    gw      = "<DEFAULT_GATEWAY>"
    dns     = ["<DNS_SERVER_1>", "<DNS_SERVER_2>"]
  }
]
```

DHCP primary NIC example for `03-templates-dhcp`:

```hcl
network_interfaces = [
  {
    bridge  = "<PROXMOX_BRIDGE>"
    vlan_id = <VLAN_ID>
    ip_mode = "dhcp"
  }
]
```

VLAN-only/trunk-style NIC example for `01-templates-api-keys` and `02-templates-generic`:

```hcl
network_interfaces = [
  {
    bridge = "<PROXMOX_BRIDGE>"
    vlan_devices = [
      {
        id = <VLAN_ID>
        ip = "<VLAN_INTERFACE_IP_CIDR>"
        gw = "<VLAN_GATEWAY>"
      }
    ]
  }
]
```

VLAN-only/trunk-style NIC example for `03-templates-dhcp`:

```hcl
network_interfaces = [
  {
    bridge  = "<PROXMOX_BRIDGE>"
    ip_mode = "none"
    vlan_devices = [
      {
        id = <VLAN_ID>
        ip = "<VLAN_INTERFACE_IP_CIDR>"
        gw = "<VLAN_GATEWAY>"
      }
    ]
  }
]
```

## Outputs

Each template emits:

- `vm_ips` — map of VM name to primary IP.
- `vm_details` — VM ID, primary IP, and configured network interfaces.
- `ansible_inventory_path` — generated `inventory.yml` path.
- `terraform_outputs_summary` — deployment count, VM names, primary IPs, inventory path, and completion flag.

## Directory Layout

```text
03-proxmox-deploy-vm/
├── README.md
├── 01-templates-api-keys/
│   ├── provider.tf
│   ├── vars.tf
│   ├── local.tf
│   ├── vm.tf
│   ├── outputs.tf
│   ├── proxmoxVMDeploy.tfvars
│   ├── templates/
│   │   └── host_inventory.tftpl
│   └── modules/
│       └── proxmox-vm/
├── 02-templates-generic/
│   ├── provider.tf
│   ├── vars.tf
│   ├── local.tf
│   ├── vm.tf
│   ├── outputs.tf
│   ├── proxmoxVMDeploy.tfvars
│   ├── templates/
│   │   └── host_inventory.tftpl
│   └── modules/
│       └── proxmox-vm/
└── 03-templates-dhcp/
    ├── provider.tf
    ├── vars.tf
    ├── local.tf
    ├── vm.tf
    ├── outputs.tf
    ├── proxmoxVMDeploy.tfvars
    ├── templates/
    │   └── host_inventory.tftpl
    └── modules/
        └── proxmox-vm/
```
