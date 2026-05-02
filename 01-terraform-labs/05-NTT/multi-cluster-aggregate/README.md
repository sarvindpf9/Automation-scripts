# multi-cluster-aggregate

Deploys OpenStack compute instances pinned to a specific host aggregate by creating a private custom flavor that embeds `aggregate_instance_extra_specs` metadata, ensuring Nova's scheduler places workloads only on hosts within the target aggregate.

---

## `testdeploy.tfvars`

Drives a single-run deployment: looks up an existing network and Glance image by name, creates a private flavor with aggregate affinity extra specs, grants the tenant access to that flavor, then launches one or more instances — optionally booting from a Cinder volume.

**Dependencies (local):**

- `terraform` / `tofu` >= 0.14 — plan and apply
- `terraform-provider-openstack` ~> 3.0.0 — OpenStack resource management
- `hashicorp/local` ~> 2.4 — writes `inventory.yml` on apply
- Admin-level OpenStack credentials — flavor creation (`openstack_compute_flavor_v2`) and project UUID resolution (`openstack_identity_project_v3`) both use the `admin_interface` provider alias

**Dependencies (OpenStack / remote):**

- The target host aggregate must already exist in Nova with its metadata key set before `tofu apply`; the flavor extra spec is matched against that metadata at scheduling time
- The Glance image named by `glance_image_name` must already be present in the target region
- The network named by `network_name` must already exist and be accessible to the tenant

**What it does:**

1. Resolves the existing Glance image (`openstack_images_image_v2`) and network (`openstack_networking_network_v2`) by name; resolves the project UUID via `openstack_identity_project_v3` using the admin endpoint.
2. Creates a private custom flavor (`${custom_name}-flavor`) with the dimensions from `flavor_vcpus`, `flavor_ram`, `flavor_disk`, and one extra spec assembled from `aggregate_instance_extra_spec` (e.g. `workload=RHEL` → `aggregate_instance_extra_specs:workload=RHEL`).
3. Grants the resolved tenant access to the private flavor via `openstack_compute_flavor_access_v2`.
4. Launches `instance_count` instances named `${custom_name}-instance-<index>`, attached to the resolved network. When `boot_from_volume = true`, attaches a `block_device` stanza with `source_type = "image"` and `destination_type = "volume"` using `volume_size`; `volume_delete_on_termination` controls whether the volume persists after instance deletion. When `boot_from_volume = false`, uses `image_id` directly.
5. Writes `inventory.yml` to the module directory via `local_file` using `templates/host_inventory.tftpl`.

### Usage

```bash
# Plan the deployment
tofu plan -var-file=testdeploy.tfvars

# Apply
tofu apply -var-file=testdeploy.tfvars

# Destroy (note: retained boot volumes are not deleted by destroy if volume_delete_on_termination = false)
tofu destroy -var-file=testdeploy.tfvars
```

### Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `openstack_user_name` | Yes | OpenStack username (must have admin role for flavor ops) |
| `openstack_tenant_name` | Yes | Target tenant/project name |
| `openstack_password` | Yes | OpenStack password |
| `openstack_auth_url` | Yes | Keystone v3 endpoint URL |
| `openstack_region` | Yes | OpenStack region name |
| `network_name` | Yes | Name of the existing network to attach instances to |
| `glance_image_name` | Yes | Name of the existing Glance image to boot from |
| `aggregate_instance_extra_spec` | Yes | Aggregate extra spec in `KEY=VALUE` form (e.g. `workload=RHEL`); assembled into `aggregate_instance_extra_specs:KEY=VALUE` on the flavor |
| `custom_name` | No | Naming prefix for all created resources (default: `ntt-agg`) |
| `flavor_vcpus` | No | vCPU count for the custom flavor (default: `2`) |
| `flavor_ram` | No | RAM in MB for the custom flavor (default: `4096`) |
| `flavor_disk` | No | Root disk GB; set `0` when `boot_from_volume = true` (default: `0`) |
| `boot_from_volume` | No | Boot instance from a Cinder volume (default: `false`) |
| `volume_size` | No | Boot volume size in GB; used only when `boot_from_volume = true` (default: `50`) |
| `volume_delete_on_termination` | No | Delete boot volume on instance termination; used only when `boot_from_volume = true` (default: `true`) |
| `ssh_key_pair` | No | Nova keypair name to inject (default: `<SSH_KEYPAIR_NAME>`) |
| `security_group` | No | Security group to apply (default: `default`) |
| `instance_count` | No | Number of instances to deploy (default: `1`) |

### Examples

```bash
# Single instance booting from ephemeral disk, pinned to aggregate workload=RHEL
tofu apply -var-file=testdeploy.tfvars \
  -var 'network_name=tenant-net' \
  -var 'glance_image_name=ubuntu-22.04' \
  -var 'aggregate_instance_extra_spec=workload=RHEL'

# Two instances booting from retained Cinder volumes (volumes survive destroy)
tofu apply -var-file=testdeploy.tfvars \
  -var 'boot_from_volume=true' \
  -var 'volume_size=100' \
  -var 'volume_delete_on_termination=false' \
  -var 'instance_count=2'
```

### Aggregate affinity mechanism

Nova's filter scheduler uses `AggregateInstanceExtraSpecsFilter` to match flavor extra specs with host aggregate metadata. The flavor created by this module sets one extra spec derived from `aggregate_instance_extra_spec` — for example `workload=RHEL` produces `aggregate_instance_extra_specs:workload=RHEL`. For placement to succeed, the target host aggregate must already have the same key/value in its metadata — set this with:

```bash
openstack aggregate set --property <KEY>=<VALUE> <AGGREGATE_NAME>
```

If the aggregate metadata does not match the flavor extra spec at scheduling time, Nova returns a `No valid host` error and the instance fails to build.

### Boot from volume behaviour

| Scenario | `boot_from_volume` | `flavor_disk` | `volume_delete_on_termination` | Result |
| -------- | ------------------ | ------------- | ------------------------------ | ------ |
| Ephemeral disk | `false` | > 0 | n/a | Instance boots from image; disk destroyed with instance |
| Boot volume, auto-delete | `true` | `0` | `true` | Cinder volume deleted when instance is terminated |
| Boot volume, retained | `true` | `0` | `false` | Cinder volume persists after `tofu destroy`; must be cleaned up manually |

When `boot_from_volume = true` the `image_id` at the instance level is set to `null`; Nova derives the boot image from the `block_device` stanza instead. Setting `flavor_disk` to a non-zero value alongside `boot_from_volume = true` is harmless but wastes ephemeral quota.

### Ansible inventory

`inventory.yml` is written to the module directory on every `tofu apply`. The template at `templates/host_inventory.tftpl` sets `ansible_ssh_private_key_file: "~/.ssh/id_rsa"` — verify this path matches your local keypair before running Ansible. Add `inventory.yml` to `.gitignore` to avoid committing generated artefacts:

```bash
echo "inventory.yml" >> .gitignore
```

### Outputs

| Output | Description |
| ------ | ----------- |
| `vm_ip_map` | Map of VM name → assigned IP address |
| `flavor_name` | Name of the custom flavor created |
| `flavor_extra_specs` | Extra specs set on the flavor (aggregate affinity constraint) |
| `image_name` | Glance image used for instance creation |
| `network_name` | Network the instances are attached to |
| `boot_volume_policy` | Effective boot volume policy: `delete-on-termination`, `retain`, or `ephemeral-disk` |
| `ansible_inventory_path` | Path to the generated `inventory.yml` file |
| `terraform_outputs_summary` | Consolidated map: VM count, names, IP map, inventory path |
