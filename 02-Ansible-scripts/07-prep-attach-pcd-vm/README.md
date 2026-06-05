# 07-prep-attach-pcd-vm

Ansible playbooks to clone Proxmox VMs from an existing template, render cloud-init user/network snippets, and configure VM networking and start behavior. This directory is intended for controller-driven deployment with inventory and group variables managed in `inventory.yaml` and `group_vars/all.yml`.

## Files

```text
07-prep-attach-pcd-vm/
├── ansible.cfg
├── inventory.yaml
├── requirements.txt
├── requirements.yml
├── scripts/
│   └── build-dhcp-inventory.py  # build generated guest inventory from Proxmox/QGA data
├── examples/
│   ├── launch-multi-nic.yml
│   └── launch-single-nic.yml
├── group_vars/all.yml
├── playbooks/
│   ├── attach-pcd-hostagent.yml  # install pcdctl and attach guest VMs to PCD
│   ├── create-vms.yml
│   ├── decommission-pcd-hosts.yml # decommission PCD hosts and unmount PCD storage
│   ├── delete-vms.yml
│   ├── dhcp-to-static.yml        # convert DHCP netplan interfaces to static entries
│   └── prepare-pcd-storage.yml   # add hosts entries and configure PCD NFS paths
├── tasks/
│   ├── cloud-ctl.yml              # download and execute pcdctl setup
│   ├── clone-vms.yml
│   ├── delete-preflight.yml
│   ├── delete-vms.yml
│   ├── decomm-hosts.yml           # decommission guard, storage cleanup, pcdctl decommission
│   ├── decomm-precheck.yml
│   ├── dhcp-to-static.yml         # task file used by playbooks/dhcp-to-static.yml
│   ├── generate-guest-inventory.yml
│   ├── hostagent.yml              # configure pcdctl and run pcdctl prep-node
│   ├── prepare-pcd-storage.yml    # /etc/hosts, directories, ownership, fstab
│   ├── preflight.yml
│   └── render-snippets.yml
└── templates/
    ├── netplan-static.yaml.j2     # legacy single-interface static netplan template
    ├── network-data.yaml.j2
    ├── proxmox-net.yml.j2
    ├── user-data.yaml.j2
    └── vm-ip-list.yml.j2
```

## Prerequisites

- Python 3 and `pip`
- `ansible` installed on the controller
- `ansible-galaxy` available for collection install
- Proxmox API access with a user capable of cloning and deleting VMs
- Existing Proxmox template VM present on the target node
- `snippet_directory` available on the Proxmox node and writable by Proxmox

## Setup

### Prepare the control node

Create a local Python virtual environment in this template directory and install all Python dependencies inside it. Keep the venv activated whenever you run `ansible-playbook`, `ansible-galaxy`, or `ansible-lint` for this template.

```bash
cd 02-Ansible-scripts/07-prep-attach-pcd-vm

# Create and activate an isolated local environment.
python3 -m venv .venv
source .venv/bin/activate

# Keep packaging tools current inside the venv, then install controller deps.
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt

# Install the required Ansible collection.
ansible-galaxy collection install -r requirements.yml
```

Verify the control-node environment:

```bash
source .venv/bin/activate
ansible --version
ansible-galaxy collection list community.proxmox
python3 -c "import proxmoxer, requests; print('controller Python dependencies OK')"
ansible-playbook --syntax-check playbooks/create-vms.yml
```

If you open a new shell, reactivate the venv before running the playbooks:

```bash
cd 02-Ansible-scripts/07-prep-attach-pcd-vm
source .venv/bin/activate
```

### Filling in group_vars/all.yml

Every `<PLACEHOLDER>` in `group_vars/all.yml` must be replaced with a real value before running any playbook. The preflight task asserts that `template_vm_id` and every per-VM `vm_id` are bare integers — leaving them as placeholder strings causes the first assertion to fail with:

```text
"assertion": "template_vm_id is number"
```

**Required types:**

- `template_vm_id`, `vm_id` — bare integer, no quotes (e.g. `9000`, not `"9000"` or `<TEMPLATE_VM_ID>`)
- `ip` fields — CIDR notation (e.g. `192.168.10.50/24`)
- `proxmox_api_user` — must include realm suffix (e.g. `root@pam` or `ansible@pve`)

Concrete filled-in example — single node, two VMs with a single NIC each:

```yaml
proxmox_api_host: 192.168.1.10        # <-- your Proxmox node IP or hostname
proxmox_api_port: 8006
proxmox_api_user: root@pam            # <-- include realm
proxmox_api_password: "changeme"      # <-- use Vault in production
proxmox_validate_certs: false
proxmox_api_timeout: 300

proxmox_node: pve-node-1              # <-- node name as shown in Proxmox UI
template_vm_id: 9000                  # <-- integer; VMID of your template
template_vm_name: ubuntu-24-04-tmpl
datastore_id: local-lvm
cloudinit_drive_datastore_id: local-lvm
snippet_datastore_id: local
snippet_directory: /var/lib/vz/snippets

ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu
cloud_init_user_password: "changeme"
vm_name_prefix: jp1

vms:
  web-01:
    vm_name: web-01
    vm_id: 201                        # <-- integer; must be unique, range 100–999999
    memory_mb: 4096
    cores: 2
    sockets: 1
    disk_size_gb: 50
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        ip: 192.168.100.21/24         # <-- CIDR notation
        gw: 192.168.100.1
        dns:
          - 8.8.8.8
        vlan_devices: []
  web-02:
    vm_name: web-02
    vm_id: 202
    memory_mb: 4096
    cores: 2
    sockets: 1
    disk_size_gb: 50
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        ip: 192.168.100.22/24
        gw: 192.168.100.1
        dns:
          - 8.8.8.8
        vlan_devices: []
```

Edit `inventory.yaml` to set `ansible_host` and `ansible_user` for the Proxmox node. Store `proxmox_api_password` with Ansible Vault or pass it at runtime with `-e proxmox_api_password=<VALUE>`.

## Usage

### Workflow commands

Run these from `02-Ansible-scripts/07-prep-attach-pcd-vm` with the virtual environment activated. Replace placeholders with site-specific values or move them into override YAML files.

1. Create Proxmox VM(s) and generate guest inventory:

```bash
ansible-playbook playbooks/create-vms.yml \
  -e @<VM_OVERRIDES_YAML>
```

2. Prepare PCD guest storage, `/etc/hosts`, `/etc/fstab`, and NFS mounts:

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/prepare-pcd-storage.yml \
  -e @<PCD_STORAGE_OVERRIDES_YAML>
```

Example storage override:

```yaml
# pcd-storage-override.yml
pcd_storage_host_entries:
  - ip: <IP_ADDRESS>
    names:
      - <FQDN>
      - <HOST_ALIAS>
```

3. Install `pcdctl` and attach the guest VM(s) to PCD:

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/attach-pcd-hostagent.yml \
  -e pcd_region_portal=<PCD_REGION_PORTAL_URL> \
  -e cloud_username=<PCD_USERNAME> \
  -e cloud_password=<PCD_PASSWORD> \
  -e cloud_project_name=<PCD_PROJECT_NAME> \
  -e cloud_region_name=<PCD_REGION_NAME>
```

4. Decommission PCD host(s), comment PCD storage fstab entries, unmount PCD storage, and run `pcdctl decommission-node`:

> **Decommissioning assumption:** before running this play, the host is expected to have its PCD roles already removed and to appear in an unauthorized state in the PCD UI. This play does not extensively check whether the host still has current roles, VMs, volumes, or other cloud resources mapped to it.

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/decommission-pcd-hosts.yml
```

5. Delete the Proxmox VM(s) defined in `vms`:

```bash
ansible-playbook playbooks/delete-vms.yml \
  -e @<VM_OVERRIDES_YAML>
```

Optional DHCP-to-static conversion for guest VM(s):

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/dhcp-to-static.yml
```

```bash
ansible-playbook playbooks/create-vms.yml
```

Delete the VMs defined in the same `vms` map:

```bash
ansible-playbook playbooks/delete-vms.yml
```

Install `pcdctl` and attach generated guest VMs to PCD:

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/attach-pcd-hostagent.yml \
  -e pcd_region_portal=<PCD_REGION_PORTAL_URL> \
  -e cloud_username=<PCD_USERNAME> \
  -e cloud_password=<PCD_PASSWORD> \
  -e cloud_project_name=<PCD_PROJECT_NAME> \
  -e cloud_region_name=<PCD_REGION_NAME>
```

Prepare guest storage paths, ownership, `/etc/fstab`, and required `/etc/hosts` entries:

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/prepare-pcd-storage.yml \
  -e '{"pcd_storage_host_entries": [{"ip": "<IP_ADDRESS>", "names": ["<FQDN>", "<HOST_ALIAS>"]}]}'
```

Use an override YAML file when you need to keep `/etc/hosts` input readable or reusable:

```yaml
# pcd-storage-override.yml
pcd_storage_host_entries:
  - ip: <IP_ADDRESS>
    names:
      - <FQDN>
      - <HOST_ALIAS>
```

```bash
ansible-playbook \
  -i generated/vm-inventory.yml \
  playbooks/prepare-pcd-storage.yml \
  -e @pcd-storage-override.yml
```

Multiple `/etc/hosts` entries can be supplied in the same override file:

```yaml
# pcd-storage-override.yml
pcd_storage_host_entries:
  - ip: <IP_ADDRESS_1>
    names:
      - <FQDN_1>
      - <HOST_ALIAS_1>
  - ip: <IP_ADDRESS_2>
    names:
      - <FQDN_2>
      - <HOST_ALIAS_2>
```

The `/etc/fstab` entries are fixed in `tasks/prepare-pcd-storage.yml` and are applied by the same play:

```text
10.96.7.20:/mnt/nfsshare/glance      /var/opt/imagelibrary/data      nfs   vers=4,proto=tcp   0       0
10.96.7.20:/mnt/nfsshare/ephemeral   /opt/data/instances             nfs   vers=4,proto=tcp   0       0
```

Before writing `/etc/fstab`, the play checks for an existing matching fstab line and whether each mountpoint is already mounted; entries that already satisfy either condition are skipped. After updating `/etc/fstab`, the play runs `systemctl daemon-reload` when the file changed, then runs `mount -a`. Recursive ownership is still attempted when `pf9` or `pf9group` is absent, but the play continues if the OS cannot resolve the account or group yet.

Override any variable with `-e`:

```bash
ansible-playbook playbooks/create-vms.yml \
  -e proxmox_api_host=192.168.1.10 \
  -e proxmox_node=pve-node-1
```

Use an example vars file for the VM launch shape and keep Proxmox connection settings in `group_vars/all.yml`:

```bash
ansible-playbook playbooks/create-vms.yml -e @examples/launch-single-nic.yml
ansible-playbook playbooks/create-vms.yml -e @examples/launch-multi-nic.yml
```

## Overriding variables with an extra-vars file

Any variable defined in `group_vars/all.yml` can be overridden at runtime by passing a YAML file with `-e @<file>`. Ansible's extra-vars have the highest variable precedence — they win over everything in `group_vars`.

```bash
ansible-playbook playbooks/create-vms.yml -e @my-vars.yml
```

### What stays in `group_vars/all.yml`

The following are site-wide settings that rarely change between runs. They must be filled in `all.yml` (or overridden explicitly in your extra-vars file if they differ between environments):

| Variable | Why it belongs in all.yml |
| ---- | ---- |
| `proxmox_api_host` | Fixed per Proxmox cluster |
| `proxmox_api_port` | Fixed per Proxmox cluster |
| `proxmox_api_user` | Fixed per operator/service account |
| `proxmox_api_password` | Site credential — use Vault |
| `proxmox_node` | Target node, fixed per environment |
| `template_vm_id` / `template_vm_name` | Source template, fixed per site |
| `datastore_id` / `cloudinit_drive_datastore_id` | Storage layout, fixed per site |
| `snippet_datastore_id` / `snippet_directory` | Snippet path, fixed per node |

### What to pass in the extra-vars file

These change per deployment and are the natural candidates for your `-e @` file:

| Variable | Notes |
| ---- | ---- |
| `vms` | Full VM definition map — see note below on replacement |
| `ssh_public_key_path` | Operator key, may differ per user |
| `cloud_init_user` | Cloud-init username for the guest OS |
| `cloud_init_user_password` | Per-deployment credential |
| `start_vms` | Override to `false` to clone without booting |
| `detach_cloudinit_drive` | Override to `false` to keep the cloud-init drive attached |

### Important: dict variables are fully replaced, not merged

When your extra-vars file defines `vms:`, it **replaces the entire `vms` dict** from `all.yml`. Ansible does not deep-merge dicts across variable precedence layers. This means:

- You cannot pass a file that only changes one VM's memory while inheriting the rest from `all.yml`.
- Your extra-vars file must contain the **complete** `vms` definition for the run.

The same applies to any other dict variable you override.

### Example: minimal extra-vars file

This file overrides `vms`, `ssh_public_key_path`, and `cloud_init_user`. All Proxmox connection settings, node, template, and storage values are read from `group_vars/all.yml`.

```yaml
# my-vms.yml
# Proxmox connection settings NOT defined here — they come from group_vars/all.yml:
#   proxmox_api_host, proxmox_api_user, proxmox_api_password,
#   proxmox_node, template_vm_id, template_vm_name,
#   datastore_id, cloudinit_drive_datastore_id, snippet_datastore_id

ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu

vms:
  app-01:
    vm_name: app-01
    vm_id: 201
    memory_mb: 4096
    cores: 2
    sockets: 1
    disk_size_gb: 50
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        ip: 192.168.100.21/24
        gw: 192.168.100.1
        dns:
          - 8.8.8.8
        vlan_devices: []
```

```bash
ansible-playbook playbooks/create-vms.yml -e @my-vms.yml
```

### Example: extra-vars file that also overrides connection settings

Use this pattern when deploying to a different Proxmox cluster or node than the one configured in `all.yml`.

```yaml
# staging-cluster.yml
proxmox_api_host: 10.0.0.5
proxmox_api_user: ansible@pve
proxmox_api_password: "vault_or_runtime_secret"
proxmox_node: pve-staging-01
template_vm_id: 8000
template_vm_name: ubuntu-24-staging-tmpl
datastore_id: ceph-pool
cloudinit_drive_datastore_id: ceph-pool

ssh_public_key_path: ~/.ssh/staging_rsa.pub
cloud_init_user: ubuntu

vms:
  staging-01:
    vm_name: staging-01
    vm_id: 901
    memory_mb: 8192
    cores: 4
    sockets: 1
    disk_size_gb: 100
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 200
        ip: 10.0.0.91/24
        gw: 10.0.0.1
        dns:
          - 10.0.0.1
        vlan_devices: []
```

```bash
ansible-playbook playbooks/create-vms.yml -e @staging-cluster.yml
```

## What it does

1. Runs preflight checks to validate VM names, VM IDs, IP addresses, and VLAN subinterface reuse.
2. Renders cloud-init `user-data` and `network-data` snippets from `group_vars/all.yml` and Jinja2 templates.
3. Queries the Proxmox node for existing VMIDs, then clones and configures only VMs that do not already exist — re-runs are safe for deployed VMs (see [Re-run behavior](#re-run-behavior)).
4. Optionally starts VMs and detaches the temporary cloud-init drive after boot.

## Playbooks

### `playbooks/create-vms.yml`

Clones and configures VMs on the target Proxmox node using `tasks/preflight.yml`, `tasks/render-snippets.yml`, and `tasks/clone-vms.yml`. When `generated_guest_inventory_enabled: true`, it then runs `tasks/generate-guest-inventory.yml` to write a guest inventory with static IPs from `vms` and DHCP IPs from QEMU Guest Agent data.

### `playbooks/delete-vms.yml`

Deletes VMs defined in `vms`, running `tasks/delete-preflight.yml` before `tasks/delete-vms.yml`.

### `playbooks/dhcp-to-static.yml`

Runs against guest VMs (not the Proxmox node) to convert a DHCP-assigned interface to a static netplan entry. Reads the current IP, prefix, gateway, and nameservers from live facts and writes a permanent `/etc/netplan/50-cloud-init.yaml`. Also disables cloud-init network management so the static config survives reboots. See [DHCP-to-static conversion](#dhcp-to-static-conversion) for full usage.

## Variables

| Variable | Required | Description |
| ---- | ---- | ---- |
| `proxmox_api_host` | Yes | Proxmox API hostname or IP, without scheme |
| `proxmox_api_port` | No | Proxmox API port, default `8006` |
| `proxmox_api_user` | Yes | API username with realm, e.g. `root@pam` or `ansible@pve` |
| `proxmox_api_password` | Yes | API password; use Vault or runtime extra-vars |
| `proxmox_validate_certs` | No | TLS verification toggle |
| `proxmox_node` | Yes | Target Proxmox node name as shown in the UI |
| `template_vm_id` | Yes | Source template VMID — **must be a bare integer**, e.g. `9000` |
| `template_vm_name` | Yes | Source template VM name |
| `datastore_id` | Yes | Target datastore for the cloned VM disk |
| `cloudinit_drive_datastore_id` | Yes | Datastore for the temporary cloud-init drive |
| `snippet_datastore_id` | Yes | Datastore ID used in Proxmox `cicustom` paths |
| `snippet_directory` | Yes | Filesystem path on the Proxmox node for snippets |
| `ssh_public_key_path` | Yes | Controller-side public key path injected into cloud-init |
| `cloud_init_user` | No | Cloud-init user, default `ubuntu` |
| `cloud_init_user_password` | No | Password set through cloud-init |
| `vm_name_prefix` | No | Optional prefix prepended to every `vms.*.vm_name`; leave empty to preserve VM names exactly as defined |
| `vms` | Yes | Map of VM definitions; each `vm_id` must be a bare integer |
| `disk_format` | No | Disk image format: `raw` (default, works on LVM-thin and directory storage) or `qcow2` (directory-type storage only — local dir, NFS, CIFS). Using `qcow2` against an LVM-thin pool returns a 500 error from Proxmox. |
| `start_vms` | No | Start VMs after clone/configure |
| `detach_cloudinit_drive` | No | Remove the temporary cloud-init `ide2` device after start |
| `delete_force` | No | Force stop/delete behavior in `delete-vms.yml` |
| `delete_purge` | No | Remove VMID from backup/replication/HA references during delete |
| `delete_remove_snippets` | No | Remove rendered user-data and network-data snippets during delete |
| `qemu_agent_enabled` | No | Enable the QEMU Guest Agent in the VM config; default `false` |
| `qemu_agent_fstrim_cloned_disks` | No | Run guest-trim after a disk move or migration; default `true`, takes effect only when `qemu_agent_enabled: true` |
| `qemu_agent_freeze_fs_on_backup` | No | Freeze/thaw guest filesystems for consistent snapshots; default `true`, takes effect only when `qemu_agent_enabled: true` |
| `generated_guest_inventory_enabled` | No | Build `generated_guest_inventory_path` after VM creation; default `true` |
| `generated_guest_inventory_path` | No | Generated guest inventory path relative to this directory, default `generated/vm-inventory.yml` |
| `generated_guest_inventory_user` | No | SSH user written into the generated guest inventory, default `ubuntu` |
| `generated_guest_inventory_ssh_private_key_path` | No | Local private key path written into the generated guest inventory. Leave empty to derive it from `ssh_public_key_path` by removing `.pub`. |
| `guest_agent_inventory_initial_delay_seconds` | No | Delay before QGA polling starts for DHCP VMs, default `90` |
| `guest_agent_inventory_max_wait_seconds` | No | Maximum QGA polling window for DHCP IP discovery, default `900` |
| `guest_agent_inventory_poll_interval_seconds` | No | Poll interval for QGA DHCP IP discovery, default `10` |

## VM customization

The `vms` map in `group_vars/all.yml` controls VM settings and network layout.

- Each VM entry requires `vm_name`, `vm_id` (integer), `memory_mb`, `cores`, `sockets`, `disk_size_gb`, and `network_interfaces`.
- `vm_name_prefix` is prepended to every VM name when set. For example, `vm_name_prefix: jp1` and `vm_name: web-01` creates `jp1-web-01`; an empty prefix preserves `web-01`.
- `network_interfaces` are rendered in order as `net0`, `net1`, etc.
- Proxmox may auto-assign NIC MACs. On first boot, the cloud-init user-data script reads the actual virtio NIC order, guest interface names, and learned MAC addresses, then rewrites `/etc/netplan/50-cloud-init.yaml` so placeholder `eth0`, `eth1`, etc. become the real guest names such as `ens18`, `ens19`.
- Set `macaddr` on a NIC only when you need to preserve or supply a specific MAC address. When set, the same MAC is written into both Proxmox NIC config and the rendered netplan.
- `vlan_id` on a network interface is applied as the Proxmox NIC VLAN tag.
- Set `dhcp4: true` on an interface to obtain an address via DHCP; omit `ip`, `gw`, and `dns` when doing so.
- VLAN subinterfaces under `vlan_devices:` are rendered inside the guest on top of the parent interface.
- Cloud-init network data is generated per VM from the same `network_interfaces` list.
- `ssh_public_key_path` points to the controller-side public key injected into the cloud-init user.

### DHCP addressing

Set `dhcp4: true` on any interface to have the guest obtain its IP from a DHCP server instead of using a static address. When `dhcp4: true` is set, omit `ip`, `gw`, and `dns` — they are ignored by the template.

The `network-data.yaml.j2` template renders the interface as:

```yaml
ethernets:
  eth0:
    dhcp4: true
```

During first boot, `/usr/local/bin/pf9-render-netplan.sh` rewrites that placeholder with the learned guest interface name and MAC. For example, if Proxmox presents the first virtio NIC as `ens18`, the applied netplan becomes:

```yaml
ethernets:
  ens18:
    match:
      macaddress: "<LEARNED_MAC_ADDRESS>"
    dhcp4: true
```

DHCP can be combined with static addressing on other NICs in the same VM — see the [mixed example](#launch-example-dhcp-on-one-nic-static-on-another) below.

When `generated_guest_inventory_enabled: true`, DHCP inventory generation requires `qemu_agent_enabled: true` and `qemu-guest-agent` running inside the template/guest. The helper script queries Proxmox VM config to map DHCP `netN` entries to MAC addresses, then queries `/agent/network-get-interfaces` and selects the non-loopback IPv4 address from the matching guest interface. This avoids using `127.0.0.1` or an IP from the wrong static/VLAN interface.

**When to use DHCP vs static:**

- Use `dhcp4: true` for management interfaces on dev/lab VMs, or when the Proxmox bridge is backed by an existing DHCP-enabled network (e.g. home lab `vmbr0` bridged to a router).
- Use static (`ip` + `gw`) for any interface that other services will reach by a fixed address, or where your cloud-init rendering must embed the IP before first boot.

#### Launch example: single NIC with DHCP

```yaml
ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu

vms:
  dev-01:
    vm_name: dev-01
    vm_id: 201
    memory_mb: 4096
    cores: 2
    sockets: 1
    disk_size_gb: 50
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        dhcp4: true
        vlan_devices: []
```

```bash
ansible-playbook playbooks/create-vms.yml -e @my-vms.yml
```

#### Launch example: DHCP on one NIC, static on another

`net0` obtains its address via DHCP; `net1` carries a static IP on a trunk bridge with VLAN subinterfaces.

```yaml
ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu

vms:
  gateway-02:
    vm_name: gateway-02
    vm_id: 302
    memory_mb: 8192
    cores: 4
    sockets: 1
    disk_size_gb: 100
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        dhcp4: true          # eth0 — management, address from DHCP
        vlan_devices: []
      - bridge: vmbr1
        vlan_devices:        # eth1 — trunk, guest VLANs with static IPs
          - id: 200
            ip: 10.200.0.31/24
          - id: 300
            ip: 10.210.0.31/24
```

```bash
ansible-playbook playbooks/create-vms.yml -e @my-vms.yml
```

---

### Launch example: single NIC

One VM with a single Proxmox NIC on `vmbr0`, tagged with VLAN 100, and a static IP configured via cloud-init. The example file overrides only the `vms` map — Proxmox connection settings and `template_vm_id` must still be filled in `group_vars/all.yml`.

```yaml
ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu

vms:
  web-01:
    vm_name: web-01
    vm_id: 201
    memory_mb: 4096
    cores: 2
    sockets: 1
    disk_size_gb: 50
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        ip: 192.168.100.21/24
        gw: 192.168.100.1
        dns:
          - 8.8.8.8
        vlan_devices: []
```

```bash
ansible-playbook playbooks/create-vms.yml -e @examples/launch-single-nic.yml
```

### Launch example: multi-NIC with guest VLANs

One VM with `net0` for management and `net1` on a trunk bridge. Cloud-init renders `eth1.200` and `eth1.300` as guest VLAN subinterfaces.

```yaml
ssh_public_key_path: ~/.ssh/id_rsa.pub
cloud_init_user: ubuntu

vms:
  gateway-01:
    vm_name: gateway-01
    vm_id: 301
    memory_mb: 8192
    cores: 4
    sockets: 1
    disk_size_gb: 100
    network_interfaces:
      - bridge: vmbr0
        vlan_id: 100
        ip: 192.168.100.31/24
        gw: 192.168.100.1
        dns:
          - 8.8.8.8
        vlan_devices: []
      - bridge: vmbr1
        vlan_devices:
          - id: 200
            ip: 10.200.0.31/24
          - id: 300
            ip: 10.210.0.31/24
```

```bash
ansible-playbook playbooks/create-vms.yml -e @examples/launch-multi-nic.yml
```

## QEMU Guest Agent

The `agent` parameter in `tasks/clone-vms.yml` maps to Proxmox's full guest-agent config string. Three flags are controlled by separate variables:

| Variable | Default | Proxmox flag | Effect |
| ---- | ---- | ---- | ---- |
| `qemu_agent_enabled` | `false` | `enabled` | Activates the QEMU Guest Agent channel in the VM config. The agent process (`qemu-guest-agent`) must be installed in the guest OS for this to do anything. |
| `qemu_agent_fstrim_cloned_disks` | `true` | `fstrim_cloned_disks` | Instructs Proxmox to issue a `fstrim` inside the guest after a full-clone or live-migration, reclaiming unused blocks on thin-provisioned storage. |
| `qemu_agent_freeze_fs_on_backup` | `true` | `freeze-fs-on-backup` | Asks the guest agent to freeze all mounted filesystems before a snapshot and thaw them afterwards, producing a consistent backup without a VM shutdown. |

`qemu_agent_fstrim_cloned_disks` and `qemu_agent_freeze_fs_on_backup` default to `true` so that they are ready to activate as soon as the agent is enabled. Changing them has no practical effect while `qemu_agent_enabled: false`.

### Enabling the QEMU Guest Agent

1. Install `qemu-guest-agent` in the guest image (or add it to your cloud-init `packages:` list).
2. Set `qemu_agent_enabled: true` in `group_vars/all.yml` or pass it at runtime.

```bash
# Enable the agent for this run only
ansible-playbook playbooks/create-vms.yml -e qemu_agent_enabled=true
```

```yaml
# group_vars/all.yml — permanent site-wide setting
qemu_agent_enabled: true
qemu_agent_fstrim_cloned_disks: true   # default; listed explicitly for clarity
qemu_agent_freeze_fs_on_backup: true   # default; listed explicitly for clarity
```

### Generated guest inventory for DHCP VMs

With `generated_guest_inventory_enabled: true`, `playbooks/create-vms.yml` writes an inventory after the clone/start tasks complete:

```yaml
generated_guest_inventory_enabled: true
generated_guest_inventory_path: generated/vm-inventory.yml
generated_guest_inventory_user: ubuntu
generated_guest_inventory_ssh_private_key_path: ""
guest_agent_inventory_initial_delay_seconds: 90
guest_agent_inventory_max_wait_seconds: 900
guest_agent_inventory_poll_interval_seconds: 10
```

For static VMs, the generated inventory uses the first NIC `ip` value from `vms`. For DHCP VMs, it polls QEMU Guest Agent and writes the resolved address. If `generated_guest_inventory_ssh_private_key_path` is empty or accidentally set to a `.pub` file, the generator writes the matching private key path without the `.pub` suffix. The generated file is ignored by Git because it contains environment-specific VM IPs and local SSH key paths.

Example generated host entry:

```yaml
all:
  children:
    proxmox_vms:
      hosts:
        "vm-01":
          ansible_host: "192.168.100.50"
          ansible_user: "ubuntu"
          ansible_ssh_private_key_file: "~/.ssh/id_rsa"
          ansible_python_interpreter: "/usr/bin/python3"
```

To disable fstrim without disabling the agent entirely (e.g. on thick-provisioned storage where fstrim serves no purpose):

```bash
ansible-playbook playbooks/create-vms.yml \
  -e qemu_agent_enabled=true \
  -e qemu_agent_fstrim_cloned_disks=false
```

---

## DHCP-to-static conversion

`playbooks/dhcp-to-static.yml` runs against guest VMs after first boot to convert DHCP-assigned addresses into permanent static netplan entries. By default it converts every ethernet stanza in the target netplan file with `dhcp4: true`. It reads each current IP and prefix from live Ansible facts, updates only those DHCP-enabled ethernet stanzas, and preserves other ethernet/VLAN config such as interfaces with `dhcp4: false`. It also drops a cloud-init override at `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` so cloud-init does not overwrite the static config on the next reboot.

> **Target host:** the IP address in `-i <IP>,` is the **guest VM's IP**, not the Proxmox hypervisor. This playbook SSHes directly into the guest OS to read its network state and write the netplan config. The Proxmox API is not used.

**Requirements:** the VM must be running and reachable over SSH. The SSH user must have sudo access (passwordless, or supply `ansible_become_pass`). Ansible facts must be gatherable — `gather_facts: true` is set by default.

### dhcp-to-static variables

| Variable | Default | Description |
| ---- | ---- | ---- |
| `target_interface` | unset | Optional single DHCP NIC to convert, e.g. `ens18`. When unset, all ethernets with `dhcp4: true` in `netplan_config_file` are converted. |
| `target_interfaces` | unset | Optional list of DHCP NICs to convert, e.g. `['ens18', 'ens19']`. Takes precedence over `target_interface`. |
| `netplan_config_file` | `/etc/netplan/50-cloud-init.yaml` | Netplan file to update in place. Non-target interface and VLAN config is preserved. |
| `nameservers` | `ansible_facts['dns']['nameservers']` (gathered from host), then `['8.8.8.8']` | List of nameserver IP addresses to write into the static netplan config. When set, this value takes priority over whatever the host currently reports via gathered DNS facts. Accepts one or more IPs. |
| `target_hosts` | `all` | Ansible host pattern; useful when the inventory contains more hosts than you want to convert in a single run. |

### dhcp-to-static usage

Convert all DHCP-enabled ethernets on a single VM (inline inventory):

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i 192.168.100.21, \
  -u ubuntu --private-key ~/.ssh/id_rsa \
  -e ansible_become_pass=<sudo_password>
```

Convert a specific named interface:

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i 192.168.100.21, \
  -u ubuntu --private-key ~/.ssh/id_rsa \
  -e target_interface=ens18 \
  -e ansible_become_pass=<sudo_password>
```

Convert multiple specific DHCP interfaces:

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i 192.168.100.21, \
  -u ubuntu --private-key ~/.ssh/id_rsa \
  -e '{"target_interfaces": ["ens18", "ens19"]}' \
  -e ansible_become_pass=<sudo_password>
```

Write to a separate netplan file instead of overwriting the cloud-init one:

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i 192.168.100.21, \
  -u ubuntu --private-key ~/.ssh/id_rsa \
  -e netplan_config_file=/etc/netplan/99-static.yaml \
  -e ansible_become_pass=<sudo_password>
```

Override nameservers with a specific list (passed inline as a JSON array):

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i 192.168.100.21, \
  -u ubuntu --private-key ~/.ssh/id_rsa \
  -e '{"nameservers": ["10.0.0.53", "10.0.0.54"]}' \
  -e ansible_become_pass=<sudo_password>
```

Override nameservers via a vars file (preferred when targeting multiple hosts):

```yaml
# dhcp-override.yml
nameservers:
  - 10.0.0.53
  - 10.0.0.54
target_interface: ens18
```

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i inventory.yaml \
  -e @dhcp-override.yml \
  -e ansible_become_pass=<sudo_password>
```

Run against a named group from an existing inventory:

```bash
ansible-playbook playbooks/dhcp-to-static.yml \
  -i inventory.yaml \
  -e target_hosts=web_servers \
  -e ansible_become_pass=<sudo_password>
```

### What the playbook does

1. Reads and parses `netplan_config_file`.
2. Resolves target interfaces from `target_interfaces`, `target_interface`, or all ethernet stanzas with `dhcp4: true`.
3. Asserts that each target interface has `dhcp4: true` in netplan and an IPv4 address in gathered facts.
4. Resolves nameservers using the following priority: user-supplied `nameservers` variable -> `ansible_facts['dns']['nameservers']` gathered from the host -> fallback `['8.8.8.8']`.
5. Updates only the target ethernet stanzas to `dhcp4: false` with static `addresses` and `nameservers`. It adds a default route only to the interface currently holding the default route.
6. Writes `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` to prevent cloud-init from regenerating the netplan file on reboot.
7. Writes the merged netplan YAML back with a backup and runs `netplan apply` only when the file changed.

### Rendered netplan output

For DHCP interfaces `ens18` and `ens19`, where `ens18` is the default-route interface with gateway `192.168.100.1`, and a user-supplied `nameservers` list of `[10.0.0.53, 10.0.0.54]`:

```yaml
network:
  version: 2
  ethernets:
    ens18:
      dhcp4: false
      addresses:
        - 192.168.100.21/24
      routes:
        - to: default
          via: 192.168.100.1
      nameservers:
        addresses:
          - 10.0.0.53
          - 10.0.0.54
    ens19:
      dhcp4: false
      addresses:
        - 192.168.101.21/24
      nameservers:
        addresses:
          - 10.0.0.53
          - 10.0.0.54
```

Each entry in the `nameservers` list becomes a separate item under `nameservers.addresses`, which is the format netplan requires. A single-item list produces one entry; an empty list is not valid — supply at least one address.

---

## Preflight behavior

The preflight task (`tasks/preflight.yml`) validates all variables before any Proxmox API calls are made. Any unfilled `<PLACEHOLDER>` string causes an assertion failure because Jinja2's `is number` test rejects non-integer values.

| Check | Applies to |
| ---- | ---- |
| `template_vm_id` is a bare integer | create |
| Each `vm_id` is an integer in range 100–999999 | create |
| Duplicate VM name or VM ID | create + delete |
| Duplicate interface IP | create + delete |
| Duplicate VLAN subinterface IP | create + delete |

## Re-run behavior

`playbooks/create-vms.yml` is safe to re-run against already-deployed VMs. At the start of `tasks/clone-vms.yml`, the playbook calls `proxmox_vm_info` to fetch all VMIDs currently present on the node and builds an `existing_vmids` list. Each subsequent task uses that list to decide whether to act or skip.

| Task | First run / new VM | Re-run for existing VM |
| ---- | ------------------ | ---------------------- |
| Clone from template | Runs — creates the VM | Skipped — VMID already present |
| Apply hardware + cloud-init config | Runs — sets cores, memory, net, and attaches `ide2: cloudinit` | Runs — updates cores, memory, and net; `ide2` parameter is omitted to prevent the `lvcreate` conflict on the backing LVM volume |
| Resize root disk | Runs — expands to `disk_size_gb` | Runs — no-op if disk is already at or above the target size |
| Start VMs | Runs (when `start_vms: true`) | Runs — no-op if VM is already running |
| Detach cloud-init drive | Runs (when `detach_cloudinit_drive: true`) | Skipped — `ide2` was not re-attached, so there is nothing to remove |

**Why the cloud-init drive is omitted on re-runs:** attaching a cloud-init drive causes Proxmox to call `lvcreate` to back the drive with an LVM logical volume named `vm-<vmid>-cloudinit`. If that volume already exists — either because the drive was attached on the first run or because the detach step did not remove the backing LV — the Proxmox API returns a `500 Internal Server Error` and the task fails. Omitting the `ide` parameter on re-runs leaves the existing VM config untouched and avoids the conflict entirely.

**Hardware updates on re-runs:** changes to `cores`, `memory_mb`, `sockets`, or `network_interfaces` in `group_vars/all.yml` are applied on every run regardless of whether the VM already exists. The Apply task always runs; only the cloud-init drive attachment is conditional.

## Compatibility

This repository uses `community.proxmox.proxmox_kvm` and requires the `community.proxmox` collection plus Python `proxmoxer` and `requests` on the controller. The collection supports cloning and VM updates, but disk and network updates are unsafe by default; this playbook uses `update_unsafe: true` only when applying `net`, `scsi`, and `cicustom` settings.
