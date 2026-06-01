# Proxmox VM Automation with OpenTofu

This lab provides two OpenTofu template variants for deploying Ubuntu 24 VMs on Proxmox VE by cloning a cloud-init template, uploading user-data/network-data snippets, and generating an Ansible inventory.

Choose one variant and run OpenTofu from that variant directory.

## Template Options

| Directory | Proxmox API auth | Use when |
|---|---|---|
| `01-templates-api-keys` | API token via `proxmox_api_token` | You have a Proxmox API token and want non-password API auth. |
| `02-templates-generic` | Username/password via `proxmox_api_username` and `proxmox_api_password` | You want to authenticate to the Proxmox API with a normal Proxmox user/password. |

Both variants keep the same VM deployment behavior:

- Clone VMs from the configured Proxmox template VM.
- Upload cloud-init snippets to the configured snippets datastore.
- Configure multiple NICs, bridge VLAN tags, and VLAN sub-interfaces.
- Start the VM after creation.
- Detach the `ide2` cloud-init drive after first boot.
- Generate `inventory.yml` for Ansible.

## Run API Token Variant

```bash
cd 01-terraform-labs/03-proxmox-deploy-vm/01-templates-api-keys
tofu init
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Required Proxmox auth variables:

```hcl
proxmox_url       = "https://<PROXMOX_HOST>:8006"
proxmox_api_token = "<USER>@<REALM>!<TOKEN_ID>=<TOKEN_SECRET>"
```

The provider uses `api_token`, and the cloud-init drive cleanup uses the same token in the `PVEAPIToken` authorization header.

## Run Username/Password Variant

```bash
cd 01-terraform-labs/03-proxmox-deploy-vm/02-templates-generic
tofu init
tofu plan -var-file=proxmoxVMDeploy.tfvars
tofu apply -var-file=proxmoxVMDeploy.tfvars
```

Required Proxmox auth variables:

```hcl
proxmox_url          = "https://<PROXMOX_HOST>:8006"
proxmox_api_username = "<USER>@<REALM>"
proxmox_api_password = "<PROXMOX_PASSWORD>"
```

The provider uses `username` and `password`. The cloud-init drive cleanup first logs in to `/api2/json/access/ticket`, then uses the returned `PVEAuthCookie` and `CSRFPreventionToken` for the `ide2` detach call.

## Shared SSH Variables

Both variants still use SSH credentials for Proxmox node file uploads:

```hcl
proxmox_ssh_username = "<PROXMOX_NODE_SSH_USER>"
proxmox_ssh_password = "<PROXMOX_NODE_SSH_PASSWORD>"
```

These are separate from API authentication. For example, API auth may be `terraform@pam` while SSH auth may be `root`.

## Shared VM Variables

Both variants use the same VM and storage settings:

```hcl
proxmox_node         = "<PROXMOX_NODE_NAME>"
template_vm_id       = <TEMPLATE_VM_ID>
datastore_id         = "<VM_DISK_DATASTORE>"
snippet_datastore_id = "<SNIPPET_DATASTORE>"
ssh_public_key_path  = "~/.ssh/<PUBLIC_KEY>.pub"
```

The `vms` map defines VM name, VM ID, CPU, memory, disk size, and `network_interfaces`. The first NIC is used as the primary IP in outputs and in the generated Ansible inventory.

## Credentials

`proxmoxVMDeploy.tfvars` in each variant contains example secrets. Treat those files and generated OpenTofu state as sensitive. Use environment-specific values before running in your Proxmox environment.

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
└── 02-templates-generic/
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
