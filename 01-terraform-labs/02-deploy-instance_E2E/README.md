# 02-deploy-instance_E2E

End-to-end Terraform/OpenTofu module that deploys one or more OpenStack Nova instances with configurable networks, image, flavor, boot mode, cloud-init user-data, and optional Cinder volumes.

---

**Dependencies (local):**

- `opentofu` ≥ 0.14 (or `terraform` ≥ 0.14) — plan and apply
- `python3-openstackclient` — for pre-flight resource verification
- OpenStack credentials with permissions on Nova, Neutron, Cinder, and Glance
- Admin endpoint access is required when `deploy_image = true` or `create_flavor = true`

**Dependencies (OpenStack services):**

- Nova (compute), Neutron (networking), Cinder (block storage), Glance (image)

**What it does:**

1. **Networks** — creates one Neutron network + subnet per entry in `networks_to_create`; if the list is empty, looks up the target network by `vm_network_name`. Instances are always attached to `vm_network_name`.
2. **Image** — uploads a local file to Glance when `deploy_image = true`; otherwise looks up the image by `image_name`.
3. **Flavor** — creates a new flavor with user-specified vCPUs/RAM/disk when `create_flavor = true`; otherwise uses an existing flavor by `flavor_name`.
4. **Instances** — deploys `vm_count` instances named `demo-<vm_name>-1`, `demo-<vm_name>-2`, … using the selected flavor, security group, and optional key pair.
5. **Boot mode** — boots from ephemeral disk (`boot_from_volume = false`) or from a new Cinder boot volume (`boot_from_volume = true`); `boot_volume_delete_on_termination` controls persistence after destroy.
6. **Data volumes** — optionally attaches one independent Cinder data volume per instance when `deploy_volume = true`.
7. **Cloud-init** — applies user-data from the inline `cloud_init_config` variable, or falls back to `cloud-init.yaml` from the module directory when the variable is empty.

## Usage

```bash
# Initialise providers
tofu init

# Plan with defaults (ephemeral boot, existing network, existing flavor)
tofu plan -var-file testdeploy.tfvars

# Apply
tofu apply -var-file testdeploy.tfvars

# Destroy all resources
tofu destroy -var-file testdeploy.tfvars
```

## Options

All variables can be set in `testdeploy.tfvars` or overridden with `-var` flags.

| Variable | Required | Default | Description |
| -------- | -------- | ------- | ----------- |
| `openstack_user_name` | Yes | — | OpenStack username |
| `openstack_tenant_name` | Yes | — | OpenStack project / tenant name |
| `openstack_password` | Yes | — | OpenStack password |
| `openstack_auth_url` | Yes | — | Keystone v3 endpoint URL |
| `openstack_region` | Yes | — | OpenStack region name |
| `vm_name` | No | `node` | Name suffix; instances are named `demo-<vm_name>-<index>` |
| `vm_count` | No | `1` | Number of identical instances to deploy |
| **Flavor** | | | |
| `flavor_name` | No | `m1.tiny` | Flavor name — used for creation or lookup |
| `create_flavor` | No | `false` | `true` = create a new flavor; `false` = use existing by `flavor_name` |
| `flavor_vcpus` | No | `1` | vCPUs for new flavor (`create_flavor = true`) |
| `flavor_ram_mb` | No | `512` | RAM in MB for new flavor (`create_flavor = true`) |
| `flavor_disk_gb` | No | `1` | Root disk in GB for new flavor (`create_flavor = true`) |
| **Network** | | | |
| `networks_to_create` | No | `[]` | List of `{name, cidr}` objects; each creates a Neutron network + subnet |
| `vm_network_name` | No | `demo-net` | Network to attach instances to; must be in `networks_to_create` or already exist |
| **Image** | | | |
| `image_name` | No | `cirros-0.6.3` | Glance image name to look up when `deploy_image = false` |
| `deploy_image` | No | `false` | Upload a local image file to Glance instead of looking one up |
| `glance_image_name` | No | `cirros-0.6.3-x86_64-disk.img` | Local filename to upload when `deploy_image = true` |
| **Boot mode** | | | |
| `boot_from_volume` | No | `false` | `true` = boot from Cinder volume; `false` = ephemeral disk |
| `boot_volume_size` | No | `20` | Boot volume size in GB (`boot_from_volume = true`) |
| `boot_volume_delete_on_termination` | No | `true` | Delete boot volume on instance destroy |
| **Data volume** | | | |
| `deploy_volume` | No | `false` | Attach a separate Cinder data volume to each instance |
| `data_volume_size` | No | `10` | Data volume size in GB |
| `volume_type` | No | `nfs-cinder` | Cinder volume type for data volumes |
| **Other** | | | |
| `cloud_init_config` | No | `""` | Inline cloud-init user-data; leave empty to use `cloud-init.yaml` |
| `security_group` | No | `default` | Security group name applied to all instances |
| `ssh_key_pair` | No | `""` | Key pair name to inject; leave empty to skip |

## Examples

### Use existing network and flavor (minimal)

```hcl
# testdeploy.tfvars
vm_name         = "web"
vm_count        = 2
vm_network_name = "existing-net"
flavor_name     = "m1.small"
image_name      = "ubuntu-22.04"
```

```bash
tofu apply -var-file testdeploy.tfvars
```

### Create multiple networks; attach VMs to one of them

```hcl
# testdeploy.tfvars
vm_name         = "app"
vm_count        = 3
vm_network_name = "lab-net-1"

networks_to_create = [
  { name = "lab-net-1", cidr = "192.168.10.0/24" },
  { name = "lab-net-2", cidr = "192.168.20.0/24" },
  { name = "lab-net-3", cidr = "10.0.30.0/24" },
]

image_name = "cirros-0.6.3"
```

```bash
tofu apply -var-file testdeploy.tfvars
```

### Create a custom flavor

```hcl
# testdeploy.tfvars
create_flavor  = true
flavor_name    = "custom.4c8g"
flavor_vcpus   = 4
flavor_ram_mb  = 8192
flavor_disk_gb = 40
```

> Requires credentials with admin endpoint access.

### Boot from volume, retain volume on destroy

```hcl
# testdeploy.tfvars
boot_from_volume                  = true
boot_volume_size                  = 50
boot_volume_delete_on_termination = false
```

### Deploy 3 instances with a data volume each

```hcl
# testdeploy.tfvars
vm_count         = 3
deploy_volume    = true
data_volume_size = 20
volume_type      = "nfs-cinder"
```

### Upload a local image and deploy from it

```hcl
# testdeploy.tfvars
deploy_image      = true
glance_image_name = "ubuntu-22.04-server-cloudimg-amd64.img"
boot_from_volume  = true
boot_volume_size  = 30
```

> The image file must exist in the module directory.

### Full example — multi-network, custom flavor, boot-from-volume, data volume

```hcl
# testdeploy.tfvars
openstack_user_name   = "<OPENSTACK_USERNAME>"
openstack_tenant_name = "<OPENSTACK_PROJECT>"
openstack_password    = "<OPENSTACK_PASSWORD>"
openstack_auth_url    = "<KEYSTONE_V3_URL>"
openstack_region      = "<REGION_NAME>"

vm_name  = "prod"
vm_count = 2

create_flavor  = true
flavor_name    = "prod.2c4g20d"
flavor_vcpus   = 2
flavor_ram_mb  = 4096
flavor_disk_gb = 20

networks_to_create = [
  { name = "prod-net", cidr = "10.10.0.0/24" },
  { name = "mgmt-net", cidr = "10.20.0.0/24" },
]
vm_network_name = "prod-net"

image_name = "ubuntu-22.04"

boot_from_volume                  = true
boot_volume_size                  = 40
boot_volume_delete_on_termination = false

deploy_volume    = true
data_volume_size = 50
volume_type      = "nfs-cinder"

security_group = "default"
ssh_key_pair   = "<KEY_PAIR_NAME>"

cloud_init_config = <<-EOF
  #cloud-config
  packages:
    - curl
    - jq
  runcmd:
    - echo "hello from cloud-init" > /tmp/init.log
EOF
```

## Boot mode behaviour

| Mode | How it works |
| ---- | ------------ |
| Ephemeral (`boot_from_volume = false`) | Instance boots from the Glance image directly; disk is local to the hypervisor and deleted on termination |
| Boot-from-volume (`boot_from_volume = true`) | A Cinder volume is created from the image at launch time; `boot_volume_delete_on_termination` controls whether it persists after the instance is destroyed |

When `boot_from_volume = true`, `image_id` on the instance resource is set to `null` and boot is driven by a `block_device` stanza with `source_type = "image"` and `destination_type = "volume"`. Setting `boot_volume_delete_on_termination = false` is the correct way to preserve boot volumes for stateful workloads.

## Network behaviour

`networks_to_create` is a list of objects with `name` and `cidr`. Each entry creates one Neutron network and one IPv4 subnet. The list can have any number of entries — all are created before instances are launched.

`vm_network_name` is independent: set it to any network the instances should use. If `vm_network_name` matches a name in `networks_to_create`, the module uses the created resource directly. If not, it looks up the network via data source (the network must already exist in the project).

```hcl
networks_to_create = [                         # Creates two networks
  { name = "lab-net-1", cidr = "..." },
  { name = "lab-net-2", cidr = "..." },
]
vm_network_name = "lab-net-1"                  # VMs go to lab-net-1
```

```hcl
networks_to_create = []                        # No networks created
vm_network_name    = "existing-corporate-net"  # VMs go to existing network
```

## Cloud-init behaviour

If `cloud_init_config` is non-empty, that string is passed directly as instance `user_data`. If it is empty (the default), the module reads `cloud-init.yaml` from the module directory at plan time using `file()`.

The bundled `cloud-init.yaml` creates a local user with a plain-text password and passwordless sudo — replace or override it before deploying to any non-ephemeral or shared environment.

**Passing `cloud_init_config` via `testdeploy.tfvars`:**

```hcl
cloud_init_config = <<-EOF
  #cloud-config
  packages:
    - curl
    - jq
  runcmd:
    - echo "hello from cloud-init" > /tmp/init.log
  users:
    - name: demouser
      sudo: ["ALL=(ALL) NOPASSWD:ALL"]
      shell: /bin/bash
      lock_passwd: false
      plain_text_passwd: "changeme"
EOF
```

## Outputs

| Output | Description |
| ------ | ----------- |
| `instance_names` | List of all instance names |
| `instance_ips` | List of IPs for all instances |
| `instance_details` | Map of instance name → `{id, ip}` for all instances |
| `image_name` | Glance image used for instance creation |
| `flavor_details` | Flavor name, vCPUs, RAM (MB), and root disk (GB) |
| `vm_network_name` | Network attached to all instances |
| `created_networks` | Map of created network name → `{network_id, subnet_id, cidr}` (empty when `networks_to_create = []`) |
| `data_volume_names` | Cinder data volume names, one per instance (empty when `deploy_volume = false`) |
| `boot_mode` | Boot mode string: `ephemeral` or `boot-from-volume (N GB, ...)` |

## `testdeploy.tfvars`

> **WARNING — sensitive data:** `testdeploy.tfvars` holds OpenStack credentials. Do not commit this file with real values. The file shipped in this directory contains QA/demo environment values only; replace them before deploying to any production or customer environment.

Minimum required entries:

```hcl
openstack_user_name   = "<OPENSTACK_USERNAME>"
openstack_tenant_name = "<OPENSTACK_PROJECT>"
openstack_password    = "<OPENSTACK_PASSWORD>"
openstack_auth_url    = "<KEYSTONE_V3_URL>"
openstack_region      = "<REGION_NAME>"
flavor_name           = "<FLAVOR_NAME>"
image_name            = "<GLANCE_IMAGE_NAME>"
vm_network_name       = "<NETWORK_NAME>"
```
