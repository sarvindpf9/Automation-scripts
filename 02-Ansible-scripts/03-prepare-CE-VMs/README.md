# 03-prepare-CE-VMs

Ansible template that prepares CE VMs or bare-metal nodes by rendering static netplan configuration for the internet-facing interface, disabling DHCP on a second interface, and adding required NFS mount entries to `/etc/fstab`.

---

## `playbooks/prepare-ce-vms.yml`

Runs against the `ce_nodes` inventory group with privilege escalation enabled. The playbook can set a requested hostname, discovers or accepts the CE node network settings, writes `/etc/netplan/50-cloud-init.yaml`, applies netplan, creates NFS mount directories, and manages the requested `/etc/fstab` entries.

**Dependencies (local):**

- `ansible-core>=2.14` — install with `pip install -r requirements.txt`
- SSH access to every host in the `ce_nodes` inventory group
- A sudo-capable remote user set through `inventory.yaml`

**Dependencies (hypervisor / remote host):**

- `/bin/bash` — used for `command -v` pre-checks
- `ip` — used with JSON output to discover the routed interface and IPv4 CIDR
- `netplan` — used to apply the rendered network configuration
- sudo access for setting hostname, writing `/etc/netplan/50-cloud-init.yaml`, editing `/etc/fstab`, creating mount directories, and running `netplan apply`
- NFS client support if the configured fstab entries will be mounted by the OS

**What it does:**

1. Sets the target hostname when `ce_hostname` is not empty.
2. Checks that `ip` and `netplan` are available on each target.
3. Runs `ip -j -4 route get {{ internet_probe_ip }}` when `internet_interface_name` or `internet_interface_cidr` is not set.
4. Parses the JSON route output and derives `ce_internet_interface` from the route `dev` field unless `internet_interface_name` is set.
5. Runs `ip -j -4 addr show dev {{ ce_internet_interface }}` when `internet_interface_cidr` is not set.
6. Builds `ce_internet_cidr` from the parsed interface `local` address and `prefixlen`, unless `internet_interface_cidr` is set.
7. Sets `ce_internet_gateway` from `internet_gateway` when provided, otherwise from `ansible_facts["default_ipv4"]["gateway"]`.
8. Validates the derived netplan values and ensures the internet-facing interface is not the same as `secondary_interface_name`.
9. Creates all paths listed in `ce_fstab_entries`.
10. Adds each `ce_fstab_entries[*].line` entry to `/etc/fstab` idempotently.
11. Renders `templates/50-cloud-init.yaml.j2` to `netplan_config_path` and runs `netplan apply` when the file changes.

### Usage

```bash
# Install local Ansible dependency
pip install -r requirements.txt

# Run against hosts from inventory.yaml
ansible-playbook playbooks/prepare-ce-vms.yml
```

```bash
# Override network detection values at runtime
ansible-playbook playbooks/prepare-ce-vms.yml \
  -e internet_interface_name=ens18 \
  -e internet_interface_cidr=10.96.7.206/20 \
  -e internet_gateway=10.96.0.1
```

```bash
# Apply a hostname while preparing the CE node
ansible-playbook playbooks/prepare-ce-vms.yml \
  -e ce_hostname=<CE_HOSTNAME>
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `internet_probe_ip` | No | IP used with `ip -j -4 route get` to discover the routed interface. Default in `group_vars/all.yml` is `1.1.1.1`. |
| `ce_hostname` | No | Hostname to apply with `ansible.builtin.hostname`. Default is empty, which keeps the current hostname. |
| `netplan_config_path` | No | Destination netplan file. Default is `/etc/netplan/50-cloud-init.yaml`. |
| `internet_interface_name` | No | Explicit internet-facing interface. Default is empty, which enables route-based detection. |
| `secondary_interface_name` | No | Second interface rendered with `dhcp4: false`. Default is `ens19`. |
| `internet_interface_cidr` | No | Explicit CIDR for the internet-facing interface. Default is empty, which enables detection from `ip -j -4 addr show dev`. |
| `internet_gateway` | No | Explicit default gateway. Default is empty, which uses `ansible_facts["default_ipv4"]["gateway"]`. |
| `netplan_nameservers` | No | Nameserver list rendered under the internet-facing interface. Default contains `10.96.0.1`. |
| `ce_fstab_entries` | No | List of mount entries. Each item must include `src`, `path`, and the full `line` to write to `/etc/fstab`. |

### Examples

```bash
# Prepare CE nodes using route-based interface and CIDR detection
ansible-playbook playbooks/prepare-ce-vms.yml
```

```bash
# Prepare CE nodes with explicit netplan values
ansible-playbook playbooks/prepare-ce-vms.yml \
  -e internet_interface_name=ens18 \
  -e internet_interface_cidr=10.96.7.206/20 \
  -e internet_gateway=10.96.0.1 \
  -e secondary_interface_name=ens19
```

```bash
# Prepare CE nodes and set hostname
ansible-playbook playbooks/prepare-ce-vms.yml \
  -e ce_hostname=<CE_HOSTNAME>
```

### Inventory

`inventory.yaml` defines the `ce_nodes` group:

```yaml
---
all:
  children:
    ce_nodes:
      hosts:
        ce-node-1:
          ansible_host: <CE_NODE_HOSTNAME_OR_IP>
          ansible_user: <SSH_USER>
```

Replace `<CE_NODE_HOSTNAME_OR_IP>` and `<SSH_USER>` with environment-specific values before execution.

> **Sensitive data notice:** `inventory.yaml` is expected to contain environment-specific hostnames, IP addresses, and SSH usernames. Do not commit customer-specific inventory values unless this repository is intended to store them.

### Netplan behaviour

The rendered netplan file always has two interfaces. The internet-facing interface is detected or supplied through `internet_interface_name`; the second interface comes from `secondary_interface_name` and is rendered with DHCP disabled.

Rendered shape:

```yaml
network:
  version: 2
  ethernets:
    ens18:
      dhcp4: false
      addresses:
        - 10.96.7.206/20
      nameservers:
        addresses:
          - 10.96.0.1
      routes:
        - to: default
          via: 10.96.0.1
    ens19:
      dhcp4: false
```

### Fstab behaviour

The playbook creates each mount directory from `ce_fstab_entries[*].path`, then writes the matching `ce_fstab_entries[*].line` into `/etc/fstab`. Existing entries matching the same `src` and `path` are replaced.

Default entries:

```text
10.96.7.20:/mnt/nfsshare/glance      /var/opt/imagelibrary/data      nfs   vers=4,proto=tcp   0       0
10.96.7.20:/mnt/nfsshare/ephemeral   /opt/data/instances             nfs   vers=4,proto=tcp   0       0
```

### Pre-check behaviour

| Check | Applies to |
| ----- | ---------- |
| `command -v ip` must succeed on the target | attach + detach |
| `command -v netplan` must succeed on the target | attach + detach |
| `ce_internet_interface`, `ce_internet_cidr`, `ce_internet_gateway`, and `secondary_interface_name` must be non-empty | attach + detach |
| `ce_internet_interface` must not equal `secondary_interface_name` | attach + detach |

### Failure behaviour

The playbook fails before writing netplan when it cannot derive or validate the required network values. If `netplan apply` fails, Ansible reports the handler failure after the template write, and the previous netplan file backup is retained because the template task uses `backup: true`.

#### Verification

```bash
# Review rendered netplan on a target
ansible ce_nodes -b -m ansible.builtin.command \
  -a 'cat /etc/netplan/50-cloud-init.yaml'

# Verify fstab entries on a target
ansible ce_nodes -b -m ansible.builtin.command \
  -a 'grep -E "/var/opt/imagelibrary/data|/opt/data/instances" /etc/fstab'
```

#### Example outputs

```
ce-node-1 | CHANGED | rc=0 >>
network:
  version: 2
  ethernets:
    ens18:
      dhcp4: false
      addresses:
        - 10.96.7.206/20
      nameservers:
        addresses:
          - 10.96.0.1
      routes:
        - to: default
          via: 10.96.0.1
    ens19:
      dhcp4: false
```
