---
name: openstack-ansible-play
description: "Use this skill when the user asks to write, generate, or fix Ansible playbooks or task files for managing workload resources on OpenStack. Triggers: 'write ansible play for openstack', 'create playbook to deploy instance', 'generate tasks for network/subnet/router/volume/security group', 'scaffold openstack ansible project', 'write openstack resource management play'. Produces functional plays using openstack.cloud collection modules with a consistent directory layout and token-retrieval flow."
---

# OpenStack Ansible Play Skill

## Behaviour

- Ask only the single most-blocking unknown before producing output.
- Never invent env-specific values (auth URLs, cloud names, project names, interface names, CIDR ranges, image names, flavor names). Use clearly marked placeholders: `<CLOUD_NAME>`, `<OS_AUTH_URL>`, `<PROJECT_NAME>`, `<IMAGE_NAME>`, etc.
- Always use FQCN for all modules (`openstack.cloud.server`, `ansible.builtin.template`, etc.).
- Resource-creation tasks always run on `localhost` with `connection: local`. Operations on deployed instances (post-deploy config) run over SSH in a second play.
- Token access from any non-localhost play: `hostvars['localhost']['keystone_token']` — never assume the token is directly available on target hosts.
- Produce only the tasks the user asked for. Do not add unrequested resources.
- **Docs are the source of truth.** Before emitting any module parameter or referencing a return value, verify it against the official documentation listed in the Documentation References section below. Use `ansible-doc openstack.cloud.<module>` locally to confirm parameter names for the exact installed collection version. Parameter names and return value keys differ between openstack.cloud major versions — never assume v1.x names apply to v2.x.

---

## Documentation References

These are the authoritative sources for all module parameters, return values, and version behaviour. Consult them before emitting any task or referencing any return key.

### openstack.cloud collection (pinned: 2.2.0)

- Collection index: https://docs.ansible.com/ansible/latest/collections/openstack/cloud/index.html
- Collection changelog (version deltas): https://github.com/openstack/ansible-collections-openstack/blob/master/CHANGELOG.rst
- clouds.yaml / openstacksdk config: https://docs.openstack.org/openstacksdk/latest/user/config/configuration.html

| Module | Official Doc |
|---|---|
| `openstack.cloud.auth` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/auth_module.html |
| `openstack.cloud.network` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/network_module.html |
| `openstack.cloud.subnet` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/subnet_module.html |
| `openstack.cloud.router` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/router_module.html |
| `openstack.cloud.security_group` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/security_group_module.html |
| `openstack.cloud.security_group_rule` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/security_group_rule_module.html |
| `openstack.cloud.server` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/server_module.html |
| `openstack.cloud.volume` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/volume_module.html |
| `openstack.cloud.server_volume` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/server_volume_module.html |
| `openstack.cloud.floating_ip` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/floating_ip_module.html |

### ansible.builtin (ships with ansible-core)

- Collection index: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/index.html

| Module | Official Doc |
|---|---|
| `ansible.builtin.set_fact` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/set_fact_module.html |
| `ansible.builtin.add_host` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/add_host_module.html |
| `ansible.builtin.template` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/template_module.html |
| `ansible.builtin.import_tasks` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/import_tasks_module.html |
| `ansible.builtin.wait_for_connection` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/wait_for_connection_module.html |

### Local verification (installed collection)

```bash
# Authoritative for the version actually installed — use this before referencing any parameter
ansible-doc openstack.cloud.<module>

# List all modules available in the installed collection
ansible-doc -l openstack.cloud
```

---

## Directory Structure

Every OpenStack Ansible project follows this layout. Generate all relevant files as a set — never a single file in isolation unless the user explicitly requests it.

```
<nn>-<slug>/
├── ansible.cfg                      # project-scoped config (roles_path, inventory)
├── requirements.yml                 # openstack.cloud collection pin
├── inventory/
│   ├── hosts.yml                    # static inventory (groups + hosts)
│   └── group_vars/
│       └── all.yml                  # vars shared across all groups
├── playbooks/
│   └── <operation>.yml             # entry-point play (deploy, teardown, validate, etc.)
├── tasks/
│   ├── token.yml                    # auth token retrieval — always reused, never inlined
│   ├── network.yml                  # neutron network + subnet tasks
│   ├── router.yml                   # router + interface tasks
│   ├── security.yml                 # security group + rule tasks
│   ├── compute.yml                  # nova server tasks
│   └── storage.yml                  # cinder volume tasks
├── vars/
│   └── <env>-vars.yml              # environment-specific variable file
└── templates/
    └── inventory.yml.j2             # Jinja2 template: rendered to inventory/hosts.yml on deploy
```

Rules:
- `tasks/` files are **never played directly** — always `import_tasks` from within a playbook play.
- `playbooks/<operation>.yml` is the only entry point for `ansible-playbook`.
- `vars/<env>-vars.yml` is loaded via `vars_files:` in the playbook; never inline vars in task files.
- `templates/*.j2` are rendered with `ansible.builtin.template` into `inventory/` or `vars/`.
- `group_vars/all.yml` holds only cross-environment defaults. Env-specific values live in `vars/<env>-vars.yml`.

---

## Canonical File Templates

### `ansible.cfg`

```ini
[defaults]
inventory       = inventory/hosts.yml
roles_path      = roles
collections_path = ~/.ansible/collections
gathering       = smart
host_key_checking = False
stdout_callback = yaml

[ssh_connection]
pipelining = True
```

### `requirements.yml`

```yaml
collections:
  - name: openstack.cloud
    version: "2.2.0"
```

Install with: `ansible-galaxy collection install -r requirements.yml`

### `inventory/hosts.yml`

```yaml
---
all:
  vars:
    cloud_name: "<CLOUD_NAME>"
    os_region_name: "<REGION_NAME>"
    os_project_name: "<PROJECT_NAME>"
  children:
    openstack_nodes:
      hosts: {}                        # populated by template task after deploy
```

### `inventory/group_vars/all.yml`

```yaml
---
ansible_user: "<SSH_USER>"
ansible_ssh_private_key_file: "<PATH_TO_KEY>"
ansible_python_interpreter: /usr/bin/python3
ansible_become_method: sudo
ansible_become_user: root
```

### `vars/<env>-vars.yml`

```yaml
---
cloud_name: "<CLOUD_NAME>"
os_auth_url: "<KEYSTONE_ENDPOINT>/v3"
os_region_name: "<REGION_NAME>"
os_project_name: "<PROJECT_NAME>"

# Network
network_name: "<NETWORK_NAME>"
subnet_name: "<SUBNET_NAME>"
subnet_cidr: "<CIDR>"                  # e.g. 192.168.100.0/24
subnet_gateway: "<GATEWAY_IP>"
dns_nameservers:
  - 8.8.8.8

# Compute
instance_name: "<INSTANCE_NAME>"
image_name: "<GLANCE_IMAGE_NAME>"
flavor_name: "<FLAVOR_NAME>"
keypair_name: "<KEYPAIR_NAME>"
security_group_name: "<SG_NAME>"

# Storage
volume_size_gb: 20
volume_type: "<VOLUME_TYPE>"           # e.g. ceph-ssd, lvm
```

---

## Token Retrieval (`tasks/token.yml`)

Always `import_tasks` this file from the first `localhost` play. Do not inline token retrieval in any other play or task file.

> Doc: https://docs.ansible.com/ansible/latest/collections/openstack/cloud/auth_module.html
> Return value: `auth_token` (string) — verified for openstack.cloud 2.x.

```yaml
---
- name: Get OpenStack auth token
  openstack.cloud.auth:
    cloud: "{{ cloud_name }}"
  register: _auth_result
  no_log: true

- name: Set keystone_token fact on localhost
  ansible.builtin.set_fact:
    keystone_token: "{{ _auth_result.auth_token }}"
  delegate_to: localhost
  run_once: true

- name: Persist token for cross-play access
  ansible.builtin.add_host:
    name: _token_store
    keystone_token: "{{ keystone_token }}"
  no_log: true
```

Token access in any subsequent play or task: `hostvars['localhost']['keystone_token']`

> `openstack.cloud.auth` reads credentials from `~/.config/openstack/clouds.yaml` using the `cloud_name` entry. No raw credentials are passed in the play.

---

## Canonical Task Patterns

### Network (`tasks/network.yml`)

> Doc (network): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/network_module.html
> Doc (subnet): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/subnet_module.html
> Version note: `provider_*` parameters require admin credentials. `external` maps to `is_router_external` in the Neutron API — verify the parameter name for the installed collection version with `ansible-doc openstack.cloud.network`.

```yaml
---
- name: Create network
  openstack.cloud.network:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ network_name }}"
    shared: false
    external: false
    provider_network_type: "{{ provider_network_type | default(omit) }}"
    provider_physical_network: "{{ provider_physical_network | default(omit) }}"
    provider_segmentation_id: "{{ provider_segmentation_id | default(omit) }}"
  register: _network

- name: Create subnet
  openstack.cloud.subnet:
    cloud: "{{ cloud_name }}"
    state: present
    network_name: "{{ network_name }}"
    name: "{{ subnet_name }}"
    cidr: "{{ subnet_cidr }}"
    gateway_ip: "{{ subnet_gateway }}"
    dns_nameservers: "{{ dns_nameservers }}"
    ip_version: 4
    enable_dhcp: true
  register: _subnet
```

### Router (`tasks/router.yml`)

> Doc: https://docs.ansible.com/ansible/latest/collections/openstack/cloud/router_module.html
> `network` = external gateway network name or ID. `interfaces` = list of subnet names or IDs to attach as internal ports.

```yaml
---
- name: Create router
  openstack.cloud.router:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ router_name }}"
    network: "{{ external_network_name }}"
    interfaces:
      - "{{ subnet_name }}"
  register: _router
```

### Security Group (`tasks/security.yml`)

> Doc (security_group): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/security_group_module.html
> Doc (security_group_rule): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/security_group_rule_module.html
> `security_group` in the rule task accepts the group name or ID. `protocol` must be a string matching the Neutron protocol list (tcp, udp, icmp, etc.).

```yaml
---
- name: Create security group
  openstack.cloud.security_group:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ security_group_name }}"
    description: "{{ security_group_description | default('Managed by Ansible') }}"
  register: _sg

- name: Allow SSH ingress
  openstack.cloud.security_group_rule:
    cloud: "{{ cloud_name }}"
    security_group: "{{ security_group_name }}"
    protocol: tcp
    port_range_min: 22
    port_range_max: 22
    remote_ip_prefix: "0.0.0.0/0"
    direction: ingress

- name: Allow ICMP ingress
  openstack.cloud.security_group_rule:
    cloud: "{{ cloud_name }}"
    security_group: "{{ security_group_name }}"
    protocol: icmp
    remote_ip_prefix: "0.0.0.0/0"
    direction: ingress
```

### Compute (`tasks/compute.yml`)

> Doc: https://docs.ansible.com/ansible/latest/collections/openstack/cloud/server_module.html
> Return value: `_server.server` (dict) — key is `server` in openstack.cloud 2.x. Fixed IP is at `_server.server.access_ipv4`. Verify return structure with `ansible-doc openstack.cloud.server` for the installed version before referencing nested keys.

```yaml
---
- name: Create instance
  openstack.cloud.server:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ instance_name }}"
    image: "{{ image_name }}"
    flavor: "{{ flavor_name }}"
    key_name: "{{ keypair_name }}"
    network: "{{ network_name }}"
    security_groups:
      - "{{ security_group_name }}"
    auto_ip: "{{ assign_floating_ip | default(false) }}"
    wait: true
    timeout: 300
  register: _server

- name: Set instance IP fact
  ansible.builtin.set_fact:
    instance_ip: "{{ _server.server.access_ipv4 }}"
```

### Volume (`tasks/storage.yml`)

> Doc (volume): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/volume_module.html
> Doc (server_volume): https://docs.ansible.com/ansible/latest/collections/openstack/cloud/server_volume_module.html
> `size` is in GiB. `volume_type` must match an existing Cinder volume type name in the cloud; use `| default(omit)` to fall back to the project default.

```yaml
---
- name: Create volume
  openstack.cloud.volume:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ volume_name }}"
    size: "{{ volume_size_gb }}"
    volume_type: "{{ volume_type | default(omit) }}"
    wait: true
  register: _volume

- name: Attach volume to instance
  openstack.cloud.server_volume:
    cloud: "{{ cloud_name }}"
    state: present
    server: "{{ instance_name }}"
    volume: "{{ volume_name }}"
  when: instance_name is defined
```

### Floating IP (`tasks/floatingip.yml`)

> Doc: https://docs.ansible.com/ansible/latest/collections/openstack/cloud/floating_ip_module.html
> Return value: `_fip.floating_ip` (dict) — the FIP address is at `_fip.floating_ip.floating_ip_address`. Verify with `ansible-doc openstack.cloud.floating_ip` for the installed collection version.

```yaml
---
- name: Assign floating IP
  openstack.cloud.floating_ip:
    cloud: "{{ cloud_name }}"
    state: present
    server: "{{ instance_name }}"
    network: "{{ external_network_name }}"
    wait: true
  register: _fip

- name: Set floating IP fact
  ansible.builtin.set_fact:
    floating_ip: "{{ _fip.floating_ip.floating_ip_address }}"
```

### Inventory template render (`tasks/render_inventory.yml`)

Renders `templates/inventory.yml.j2` into `inventory/hosts.yml` after instances are created.

```yaml
---
- name: Render dynamic inventory
  ansible.builtin.template:
    src: "../templates/inventory.yml.j2"
    dest: "{{ playbook_dir }}/../inventory/hosts.yml"
    mode: "0644"
  delegate_to: localhost
```

### `templates/inventory.yml.j2`

```yaml
---
all:
  vars:
    cloud_name: "{{ cloud_name }}"
    ansible_user: "{{ ansible_user }}"
    ansible_ssh_private_key_file: "{{ ansible_ssh_private_key_file }}"
  children:
    openstack_nodes:
      hosts:
{% for host in groups['openstack_nodes'] | default([]) %}
        {{ host }}:
          ansible_host: {{ hostvars[host]['ansible_host'] | default(host) }}
{% endfor %}
```

---

## Playbook Patterns

### Resource-only deploy (localhost, no SSH to instances)

Use when the play only creates OpenStack resources (networks, instances, volumes).

```yaml
---
- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - ansible.builtin.import_tasks: ../tasks/token.yml
    - ansible.builtin.import_tasks: ../tasks/network.yml
    - ansible.builtin.import_tasks: ../tasks/security.yml
    - ansible.builtin.import_tasks: ../tasks/compute.yml
    - ansible.builtin.import_tasks: ../tasks/render_inventory.yml
```

### Two-phase: resource creation + post-deploy instance config

Use when instances need to be configured over SSH after creation.

```yaml
---
# Phase 1: create resources from localhost
- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - ansible.builtin.import_tasks: ../tasks/token.yml
    - ansible.builtin.import_tasks: ../tasks/network.yml
    - ansible.builtin.import_tasks: ../tasks/security.yml
    - ansible.builtin.import_tasks: ../tasks/compute.yml
    - ansible.builtin.import_tasks: ../tasks/floatingip.yml
    - ansible.builtin.import_tasks: ../tasks/render_inventory.yml

# Phase 2: configure instances over SSH
- hosts: openstack_nodes
  connection: ssh
  become: true
  gather_facts: true
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - name: Wait for SSH
      ansible.builtin.wait_for_connection:
        timeout: 120

    # add configuration tasks here
```

### Teardown (state: absent)

```yaml
---
- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - ansible.builtin.import_tasks: ../tasks/token.yml

    - name: Delete instance
      openstack.cloud.server:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ instance_name }}"
        wait: true

    - name: Delete volume
      openstack.cloud.volume:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ volume_name }}"

    - name: Delete router
      openstack.cloud.router:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ router_name }}"

    - name: Delete subnet
      openstack.cloud.subnet:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ subnet_name }}"

    - name: Delete network
      openstack.cloud.network:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ network_name }}"
```

> Teardown order matters: instances → volumes → routers → subnets → networks. Never reverse this order.

---

## Variable Conventions

| Variable | Where defined | Description |
|---|---|---|
| `cloud_name` | `group_vars/all.yml` or `vars/<env>-vars.yml` | Entry in `~/.config/openstack/clouds.yaml` |
| `os_region_name` | `vars/<env>-vars.yml` | OpenStack region |
| `os_project_name` | `vars/<env>-vars.yml` | Project / tenant name |
| `keystone_token` | `set_fact` on localhost | Set by `tasks/token.yml`; cross-play via `hostvars['localhost']['keystone_token']` |
| `network_name` | `vars/<env>-vars.yml` | Neutron network name |
| `subnet_name` | `vars/<env>-vars.yml` | Subnet name |
| `subnet_cidr` | `vars/<env>-vars.yml` | Subnet CIDR block |
| `router_name` | `vars/<env>-vars.yml` | Router name |
| `external_network_name` | `vars/<env>-vars.yml` | External / provider network for router uplink and floating IPs |
| `security_group_name` | `vars/<env>-vars.yml` | Security group name |
| `instance_name` | `vars/<env>-vars.yml` | Nova server name |
| `image_name` | `vars/<env>-vars.yml` | Glance image name |
| `flavor_name` | `vars/<env>-vars.yml` | Nova flavor name |
| `keypair_name` | `vars/<env>-vars.yml` | Nova keypair name (must already exist in the project) |
| `volume_name` | `vars/<env>-vars.yml` | Cinder volume name |
| `volume_size_gb` | `vars/<env>-vars.yml` | Volume size in GB |
| `volume_type` | `vars/<env>-vars.yml` | Cinder volume type; omit to use project default |
| `instance_ip` | `set_fact` after server task | Fixed IP of the instance; set in `tasks/compute.yml` |
| `floating_ip` | `set_fact` after floating IP task | FIP address; set in `tasks/floatingip.yml` |

---

## Constraints

- Never hardcode credentials, passwords, or auth URLs in task files or playbooks — they belong in `clouds.yaml` and are referenced only via `cloud_name`.
- `tasks/token.yml` must be the first `import_tasks` in any play that calls OpenStack modules not covered by the `cloud:` parameter. For all `openstack.cloud.*` modules, use `cloud: "{{ cloud_name }}"` — the token is handled by the SDK internally.
- Teardown order is fixed: instances → volumes → routers → subnets → networks. Any other order will fail on dependency conflicts.
- Use `state: present` / `state: absent` consistently — do not use `command:` or `uri:` to wrap OpenStack CLI or REST calls when a `openstack.cloud.*` module covers the operation.
- Provider network parameters (`provider_network_type`, `provider_physical_network`, `provider_segmentation_id`) require admin credentials in the cloud; pass them as `| default(omit)` so the task degrades cleanly for non-admin users.
- `ansible.builtin.template` rendering always delegates to localhost — never run it on remote hosts.
- Do not add unrequested resources (e.g. router, floating IP) unless the user's ask implies them.
- `wait: true` is mandatory on `openstack.cloud.server` and `openstack.cloud.volume` — omitting it causes race conditions in subsequent tasks that reference the resource.

### Version-sensitive parameters

openstack.cloud v2.x introduced breaking parameter and return value changes from v1.x. Before emitting any parameter from the table below, confirm it for the pinned version (2.2.0) using `ansible-doc openstack.cloud.<module>`:

| Module | Known v1→v2 change | Check |
|---|---|---|
| `openstack.cloud.network` | `external` may be `is_router_external` in some releases | `ansible-doc openstack.cloud.network \| grep external` |
| `openstack.cloud.server` | `network` (shorthand) vs `nics` (list of dicts) for multi-NIC | Use `network` for single-NIC; use `nics` for multi-NIC per the doc |
| `openstack.cloud.server` | Return key `openstack` (v1) → `server` (v2) | Verify `_server.server.*` vs `_server.openstack.*` |
| `openstack.cloud.floating_ip` | Return key structure changed in v2 | Verify `_fip.floating_ip.floating_ip_address` |

### Module coverage check

Before falling back to `ansible.builtin.uri` or `ansible.builtin.command` for any OpenStack operation, verify there is no `openstack.cloud.*` module covering it:

```bash
ansible-doc -l openstack.cloud | grep <resource_type>
```

Only use raw REST (`uri`) or CLI (`command`) calls when no module exists for the operation and it cannot be deferred to a post-task step using a covered module.
