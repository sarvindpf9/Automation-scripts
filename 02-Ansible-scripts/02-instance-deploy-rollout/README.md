# 02-instance-deploy-rollout

Ansible play set for deploying and tearing down OpenStack Nova instances with configurable storage backend, availability zone placement, optional flavor creation, and bulk rollout support.

---

## `playbooks/deploy.yml`

Entry-point playbook that optionally creates a flavor, then loops over `range(vm_count)` to spawn one or more VMs named `<vm_base_name>-01`, `<vm_base_name>-02`, etc. Credentials are read from `~/.config/openstack/clouds.yaml` via the `cloud_name` variable; no explicit auth task is required. Fixed IPs of deployed instances are printed to console output on completion.

**Dependencies (local):**

- `ansible-core` ≥ 2.14, `openstack.cloud` collection 2.2.0 — install with `ansible-galaxy collection install -r requirements.yml`
- `~/.config/openstack/clouds.yaml` — must contain a valid entry matching `cloud_name`; no credentials are passed in the play

**Dependencies (OpenStack project):**

- Keypair named `keypair_name` must already exist in the project if provided; omit or leave empty to launch without an injected key
- Neutron network named `network_name` must already exist
- Glance image named `image_name` must already be uploaded
- If `create_flavor: false`, flavor named `flavor_name` must already exist

**What it does:**

1. Reads credentials from `~/.config/openstack/clouds.yaml` via `cloud: "{{ cloud_name }}"` on each module call — no explicit auth task
2. Creates a Nova flavor with optional `extra_specs` when `create_flavor: true` (idempotent — skips if the flavor already exists)
3. Loops over `range(vm_count)` and creates each instance; storage backend is either ephemeral disk or a Cinder volume depending on `boot_from_volume`
4. Applies `availability_zone` to each server to pin placement; omitted entirely when set to `""` so the Nova scheduler decides
5. Collects fixed IPs from the server results and prints each `<name> → <ip>` via debug output

### Setup

```bash
# Install the required collection (once per machine)
ansible-galaxy collection install -r requirements.yml

# Fill in placeholders in vars/deploy-vars.yml before running
```

### clouds.yaml configuration

openstacksdk resolves credentials from `~/.config/openstack/clouds.yaml`. The `cloud_name` variable must match an entry key in this file.

Minimal structure:

```yaml
clouds:
  <CLOUD_NAME>:
    auth:
      auth_url: <KEYSTONE_ENDPOINT>/v3
      project_name: <PROJECT_NAME>
      username: <USERNAME>
      password: <PASSWORD>
      user_domain_name: Default
      project_domain_name: Default
    region_name: <REGION_NAME>
    identity_api_version: 3
```

Multiple cloud entries are supported — add one block per environment and switch between them with `-e cloud_name=<CLOUD_NAME>`.

If your `clouds.yaml` is not at the default path, set the env variable before running:

```bash
export OS_CLIENT_CONFIG_FILE=/path/to/clouds.yaml
ansible-playbook playbooks/deploy.yml
```

Verify the entry resolves correctly before running the play:

```bash
openstack --os-cloud <CLOUD_NAME> token issue
```

### Usage

```bash
# Deploy using all defaults from vars/deploy-vars.yml
ansible-playbook playbooks/deploy.yml

# Deploy 5 VMs
ansible-playbook playbooks/deploy.yml -e vm_count=5

# Deploy with boot-from-volume (50 GiB, delete volume on teardown)
ansible-playbook playbooks/deploy.yml \
  -e boot_from_volume=true \
  -e volume_size_gb=50

# Deploy with boot-from-volume and preserve the volume after server deletion
ansible-playbook playbooks/deploy.yml \
  -e boot_from_volume=true \
  -e volume_size_gb=50 \
  -e delete_volume_on_termination=false

# Deploy into a specific availability zone
ansible-playbook playbooks/deploy.yml \
  -e availability_zone="nova:compute01"

# Create a new flavor before deploying (vcpus/ram/disk required)
ansible-playbook playbooks/deploy.yml \
  -e create_flavor=true \
  -e flavor_vcpus=4 \
  -e flavor_ram_mb=8192 \
  -e flavor_disk_gb=40

# Create a flavor with host aggregate pinning via extra_specs
ansible-playbook playbooks/deploy.yml \
  -e create_flavor=true \
  -e flavor_vcpus=4 \
  -e flavor_ram_mb=8192 \
  -e flavor_disk_gb=40 \
  -e '{"flavor_extra_specs": {"aggregate_instance_extra_specs:storage_type": "ssd"}}'
```

### Examples

Common end-to-end invocations with illustrative but env-specific values — substitute real names from your OpenStack project.

`cloud_name` must match an entry in `~/.config/openstack/clouds.yaml`. `keypair_name` is optional; omit it to launch without an injected SSH key.

```bash
# Single VM: ephemeral disk, no keypair injection
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=web \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.medium.vol \
  -e network_name=provider-vlan1001net

# Single VM: ephemeral disk, with keypair injected
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=web \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.medium.vol \
  -e keypair_name=my-key \
  -e network_name=provider-vlan1001net

# Three VMs: boot-from-volume (80 GiB), volume deleted on teardown
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=app \
  -e vm_count=3 \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.large \
  -e network_name=provider-vlan1001net \
  -e boot_from_volume=true \
  -e volume_size_gb=80

# Single VM: boot-from-volume, preserve volume after server delete
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=db \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.xlarge \
  -e network_name=provider-vlan1001net \
  -e boot_from_volume=true \
  -e volume_size_gb=200 \
  -e delete_volume_on_termination=false

# Two VMs: pinned to a specific compute host via AZ
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=cache \
  -e vm_count=2 \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.medium.vol \
  -e network_name=provider-vlan1001net \
  -e availability_zone="nova:compute01"

# Create a new flavor with SSD aggregate pinning, then deploy one VM
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=gpu \
  -e image_name=ubuntu24-lts \
  -e flavor_name=custom-4c-8g \
  -e network_name=provider-vlan1001net \
  -e create_flavor=true \
  -e flavor_vcpus=4 \
  -e flavor_ram_mb=8192 \
  -e flavor_disk_gb=40 \
  -e '{"flavor_extra_specs": {"aggregate_instance_extra_specs:storage_type": "ssd"}}'
```

### Variables

All variables are defined in `vars/deploy-vars.yml`. Any can be overridden at runtime with `-e variable=value`.

| Variable | Required | Description |
| ---- | -------- | ----------- |
| `cloud_name` | Yes | Entry name in `~/.config/openstack/clouds.yaml` |
| `vm_base_name` | Yes | Name prefix; instances become `<base>-01`, `<base>-02`, … |
| `vm_count` | No | Number of VMs to spawn (default: `1`) |
| `image_name` | Yes | Glance image name for the root disk |
| `flavor_name` | Yes | Nova flavor name — existing, or the name to create when `create_flavor: true` |
| `keypair_name` | No | Nova keypair name; must pre-exist in the project. Omit or set to `""` to launch without an injected SSH key (default: `""`) |
| `network_name` | Yes | Neutron network name for the VM NIC |
| `availability_zone` | No | AZ to pin VM placement (e.g. `nova:compute01`); empty string lets Nova scheduler decide (default: `""`) |
| `boot_from_volume` | No | `true` = Cinder volume root disk; `false` = ephemeral disk (default: `false`) |
| `volume_size_gb` | BFV only | Boot volume size in GiB (default: `20`); ignored when `boot_from_volume: false` |
| `delete_volume_on_termination` | BFV only | `true` = Nova deletes the volume with the server; `false` = volume is preserved (default: `true`) |
| `create_flavor` | No | `true` = create the Nova flavor before deploying VMs (default: `false`) |
| `flavor_vcpus` | create_flavor only | vCPU count for the new flavor (default: `2`) |
| `flavor_ram_mb` | create_flavor only | RAM in MiB for the new flavor (default: `4096`) |
| `flavor_disk_gb` | create_flavor only | Root disk size in GiB for the new flavor (default: `20`) |
| `flavor_is_public` | No | Whether the created flavor is publicly visible (default: `true`) |
| `flavor_extra_specs` | No | Dict of flavor extra_specs; pass `aggregate_instance_extra_specs:<key>: <value>` to restrict VMs to host aggregates (default: `{}`) |
| `cloud_init_enabled` | No | `true` = inject cloud-config user-data on first boot (default: `false`) |
| `cloud_init_user` | cloud_init only | OS username created on first boot (default: `ubuntu`) |
| `cloud_init_password` | cloud_init only | Plain-text password set via `chpasswd`; leave `""` for key-only access (default: `""`) |
| `cloud_init_groups` | cloud_init only | Additional groups for the user, e.g. `[docker, adm]` (default: `[]`) |
| `cloud_init_ssh_keys` | cloud_init only | List of SSH public key strings injected for `cloud_init_user` (default: `[]`) |
| `cloud_init_packages` | cloud_init only | List of packages to install on first boot; requires network at boot time (default: `[]`) |
| `cloud_init_write_files` | cloud_init only | List of `{path, content, permissions, owner}` dicts written before `runcmd` (default: `[]`) |
| `cloud_init_runcmd` | cloud_init only | List of shell commands run at the end of first boot (default: `[]`) |

### Storage backend behaviour

| `boot_from_volume` | Root disk | `volume_size_gb` applied | `delete_volume_on_termination` applied |
| ---- | -------- | ---- | ---- |
| `false` | Ephemeral (Nova-managed) | No | No |
| `true` | Cinder volume | Yes | Yes |

When `boot_from_volume: true` and `delete_volume_on_termination: false`, the Cinder volume survives server deletion and must be cleaned up manually (see teardown notes below).

### Host aggregate pinning

To restrict VM placement to a host aggregate, the aggregate must have a matching metadata property set on it, and the flavor must carry the corresponding `aggregate_instance_extra_specs` key. Example:

```bash
# On the OpenStack side (admin)
openstack aggregate set --property storage_type=ssd <AGGREGATE_NAME>

# In vars/deploy-vars.yml or as -e flag
flavor_extra_specs:
  "aggregate_instance_extra_specs:storage_type": "ssd"
```

### Cloud-init user-data

When `cloud_init_enabled: true`, the play renders `templates/cloud-init.yml.j2` and passes it to Nova as the instance user-data. The template is evaluated once per playbook run (not per VM), so all instances in a batch receive identical user-data.

The created user is granted passwordless `sudo`. Password authentication over SSH is disabled by default unless `cloud_init_password` is set (which also enables `ssh_pwauth: true` in the rendered config).

```bash
# Deploy with a named user and password
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=web \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.medium.vol \
  -e network_name=provider-vlan1001net \
  -e cloud_init_enabled=true \
  -e cloud_init_user=ops \
  -e cloud_init_password=changeme123

# Deploy with packages and a startup command (inline JSON for list values)
ansible-playbook playbooks/deploy.yml \
  -e cloud_name=my-cloud \
  -e vm_base_name=app \
  -e image_name=ubuntu24-lts \
  -e flavor_name=m1.medium.vol \
  -e network_name=provider-vlan1001net \
  -e cloud_init_enabled=true \
  -e cloud_init_user=ops \
  -e '{"cloud_init_packages": ["curl", "htop", "python3-pip"]}' \
  -e '{"cloud_init_runcmd": ["systemctl enable --now myservice"]}'
```

For multi-key cloud-init configuration, set the values in `vars/deploy-vars.yml` rather than passing them inline:

```yaml
cloud_init_enabled: true
cloud_init_user: ops
cloud_init_password: changeme123
cloud_init_groups:
  - docker
  - adm
cloud_init_packages:
  - curl
  - htop
  - docker.io
cloud_init_write_files:
  - path: /etc/myapp/config.ini
    permissions: '0640'
    owner: "root:root"
    content: |
      [settings]
      log_level = info
cloud_init_runcmd:
  - systemctl enable --now docker
  - "echo 'bootstrap done' >> /var/log/bootstrap.log"
```

The `write_files` entries are written before `runcmd` runs, so services or commands that depend on a config file being present will see it in place.

---

## `playbooks/teardown.yml`

Deletes all VMs created by `deploy.yml` for the same `vm_base_name` and `vm_count`. Does not delete networks, keypairs, or security groups.

**What it does:**

1. Reads credentials from `~/.config/openstack/clouds.yaml` via `cloud: "{{ cloud_name }}"` — no explicit auth task
2. Deletes each instance named `<vm_base_name>-01` … `<vm_base_name>-NN` in sequence, waiting for each deletion to complete (`timeout: 300`)
3. If `boot_from_volume: true` and `delete_volume_on_termination: true`, Nova removes the boot volume automatically — no extra step

### Teardown usage

```bash
# Teardown all VMs defined in vars/deploy-vars.yml
ansible-playbook playbooks/teardown.yml

# Teardown a specific count (overrides vm_count in vars file)
ansible-playbook playbooks/teardown.yml -e vm_count=3
```

### Preserved volume cleanup

When `boot_from_volume: true` and `delete_volume_on_termination: false`, boot volumes are **not** deleted by teardown. Locate and remove them manually:

```bash
openstack volume list --long | grep <VM_BASE_NAME>
openstack volume delete <VOLUME_ID>
```

---

## `playbooks/upload-image.yml`

Uploads a local image file to Glance and sets a standard set of hardware and guest-agent properties. The property set is split into a fixed base (`image_base_properties`) and an open-ended extension dict (`image_extra_properties`) so callers can add OS-type, distro, or any other Glance property without editing the base block.

**Dependencies (local):**

- `ansible-core` ≥ 2.14, `openstack.cloud` collection 2.2.0
- `~/.config/openstack/clouds.yaml` with a valid `cloud_name` entry
- The local image file must be readable by the Ansible controller process

**What it does:**

1. Verifies the local image file exists; fails immediately with a clear message if not found
2. Uploads the file to Glance via `openstack.cloud.image` with the configured disk format, container format, and visibility
3. Merges `image_base_properties` with `image_extra_properties` (extra keys override base on collision) and applies the result as Glance image properties
4. Prints the uploaded image name, Glance ID, status, and visibility on completion

### Upload usage

```bash
# Upload a private qcow2 image with default properties
ansible-playbook playbooks/upload-image.yml \
  -e cloud_name=my-cloud \
  -e image_upload_name=ubuntu24-lts \
  -e image_local_path=/tmp/ubuntu-24.04.qcow2

# Upload a public image
ansible-playbook playbooks/upload-image.yml \
  -e cloud_name=my-cloud \
  -e image_upload_name=ubuntu24-lts \
  -e image_local_path=/tmp/ubuntu-24.04.qcow2 \
  -e image_visibility=public

# Linux image with OS metadata
ansible-playbook playbooks/upload-image.yml \
  -e cloud_name=my-cloud \
  -e image_upload_name=ubuntu24-lts \
  -e image_local_path=/tmp/ubuntu-24.04.qcow2 \
  -e '{"image_extra_properties": {"os_type": "linux", "os_distro": "ubuntu"}}'

# Windows image with OS metadata
ansible-playbook playbooks/upload-image.yml \
  -e cloud_name=my-cloud \
  -e image_upload_name=windows2022 \
  -e image_local_path=/tmp/win2022.qcow2 \
  -e image_visibility=public \
  -e '{"image_extra_properties": {"os_type": "windows", "os_distro": "windows", "hw_video_model": "vga"}}'

# Raw-format image
ansible-playbook playbooks/upload-image.yml \
  -e cloud_name=my-cloud \
  -e image_upload_name=rocky9-raw \
  -e image_local_path=/tmp/rocky9.img \
  -e image_disk_format=raw \
  -e '{"image_extra_properties": {"os_type": "linux", "os_distro": "rhel"}}'
```

### Image variables

| Variable | Required | Description |
| ---- | -------- | ----------- |
| `cloud_name` | Yes | Entry name in `~/.config/openstack/clouds.yaml` |
| `image_upload_name` | Yes | Name the image will have in Glance |
| `image_local_path` | Yes | Absolute or relative path to the local image file |
| `image_disk_format` | No | Disk format: `qcow2`, `raw`, `vmdk`, `vhd`, `vhdx`, `iso` (default: `qcow2`) |
| `image_container_format` | No | Container format; use `bare` for all standard image types (default: `bare`) |
| `image_visibility` | No | `public` = all projects can use it; `private` = uploading project only (default: `private`) |
| `image_base_properties` | No | Fixed dict of hardware/guest-agent properties applied to every upload (see below) |
| `image_extra_properties` | No | Dict merged on top of `image_base_properties`; keys here override matching base keys (default: `{}`) |

### Base properties

These are set on every image uploaded by this playbook. Override individual keys via `image_extra_properties`.

| Property | Value | Purpose |
| ---- | -------- | ----------- |
| `hw_disk_bus` | `scsi` | Attaches root and data disks via the virtio-scsi controller |
| `hw_scsi_model` | `virtio-scsi` | Selects the virtio-scsi adapter model |
| `hw_machine_type` | `q35` | Uses the Q35 chipset (PCIe slots, required for virtio-scsi on some distros) |
| `hw_qemu_guest_agent` | `yes` | Enables the QEMU guest agent channel so Nova can issue quiesce/unquiesce calls |
| `os_require_quiesce` | `yes` | Requires guest quiesce before live snapshots; prevents inconsistent backups |

### Additional properties

Pass any Glance image property via `image_extra_properties`. Common additions:

```yaml
image_extra_properties:
  os_type: linux           # linux or windows — consumed by some Nova schedulers
  os_distro: ubuntu        # distro hint used by cloud tools (ubuntu, rhel, windows, etc.)
  os_version: "24.04"
  hw_video_model: vga      # override default video adapter (useful for Windows)
  hw_rng_model: virtio     # enable virtio RNG device
```
