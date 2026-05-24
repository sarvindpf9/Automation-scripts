---
name: openstack-ansible-play
description: "Use this skill when the user asks to write, generate, or fix Ansible playbooks or task files for managing workload resources on OpenStack. Triggers: 'write ansible play for openstack', 'create playbook to deploy instance', 'generate tasks for network/subnet/router/volume/security group', 'scaffold openstack ansible project', 'write openstack resource management play'. Produces functional plays using openstack.cloud collection modules with a consistent directory layout and token-retrieval flow."
---

# OpenStack Ansible Play Skill

## Rules

- Ask only the single most-blocking unknown before producing output.
- Never invent env-specific values. Use placeholders: `<CLOUD_NAME>`, `<IMAGE_NAME>`, `<FLAVOR_NAME>`, etc.
- Always use FQCN: `openstack.cloud.server`, `ansible.builtin.template`, etc.
- Resource-creation tasks run on `localhost` (`connection: local`). Post-deploy instance config runs over SSH in a second play.
- Produce only the tasks the user asked for. Do not add unrequested resources.
- `| default(omit, true)` omits both undefined vars and empty strings (e.g. `keypair_name`, `availability_zone`). `| default(omit)` only omits undefined — use the two-arg form for params that may be set to `""`.
- Declare `collections: [openstack.cloud]` at the play level; still use FQCN for `ansible.builtin.*`.
- All `openstack.cloud.*` modules handle auth internally via `cloud: "{{ cloud_name }}"`. `tasks/token.yml` is only needed when the play also makes raw `ansible.builtin.uri` calls requiring an explicit bearer token.
- `wait: true` is mandatory on `openstack.cloud.server` and `openstack.cloud.volume` — omitting it causes race conditions.
- Teardown order is fixed: instances → volumes → routers → subnets → networks.
- Before emitting any module parameter or return value key, verify with `ansible-doc openstack.cloud.<module>`. v1.x names do not apply to v2.x.

---

## Module Reference

Pinned collection: `openstack.cloud 2.2.0`
Verify locally: `ansible-doc openstack.cloud.<module>` · `ansible-doc -l openstack.cloud | grep <type>`

| Module | Doc |
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
| `openstack.cloud.compute_flavor` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/compute_flavor_module.html |
| `openstack.cloud.image` | https://docs.ansible.com/ansible/latest/collections/openstack/cloud/image_module.html |

Version-sensitive changes (v1→v2); confirm before use:

| Module | Change |
|---|---|
| `openstack.cloud.network` | `external` may be `is_router_external` — check with `ansible-doc` |
| `openstack.cloud.server` | Return key `openstack` (v1) → `server` (v2); single-NIC use `network:`, multi-NIC use `nics:` |
| `openstack.cloud.floating_ip` | Return key structure changed — verify `_fip.floating_ip.floating_ip_address` |

---

## Directory Layout

Generate all relevant files as a set. `tasks/` files are never run directly — always `import_tasks` from a playbook. Env-specific values live in `vars/<env>-vars.yml`, never inlined in tasks.

```
<nn>-<slug>/
├── ansible.cfg
├── requirements.yml
├── inventory/
│   ├── hosts.yml                    # populated by render_inventory after deploy
│   └── group_vars/
│       └── all.yml                  # SSH connection defaults
├── playbooks/
│   └── <operation>.yml             # only entry point for ansible-playbook
├── tasks/
│   ├── token.yml                    # only when raw uri calls need a bearer token
│   ├── network.yml
│   ├── router.yml
│   ├── security.yml
│   ├── compute.yml                  # single instance or bulk loop
│   ├── flavor.yml                   # gated by create_flavor flag
│   ├── image.yml                    # glance upload
│   ├── storage.yml                  # separately attached data volumes
│   └── floatingip.yml
├── vars/
│   └── <env>-vars.yml
└── templates/
    ├── cloud-init.yml.j2            # rendered via lookup() into compute.yml
    └── inventory.yml.j2
```

---

## Config Files

### `ansible.cfg`

```ini
[defaults]
inventory        = inventory/hosts.yml
roles_path       = roles
collections_path = ~/.ansible/collections
gathering        = smart
host_key_checking = False
stdout_callback  = yaml

[ssh_connection]
pipelining = True
```

### `requirements.yml`

```yaml
collections:
  - name: openstack.cloud
    version: "2.2.0"
```

`ansible-galaxy collection install -r requirements.yml`

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
      hosts: {}
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

---

## Variables (`vars/<env>-vars.yml`)

This file is the canonical input spec. Load via `vars_files:` in the playbook; never inline vars in task files.

```yaml
---
# ─── Cloud Identity ────────────────────────────────────────────────────────────
cloud_name: "<CLOUD_NAME>"             # entry in ~/.config/openstack/clouds.yaml

# ─── Network ──────────────────────────────────────────────────────────────────
network_name: "<NETWORK_NAME>"
subnet_name: "<SUBNET_NAME>"
subnet_cidr: "<CIDR>"                  # e.g. 192.168.100.0/24
subnet_gateway: "<GATEWAY_IP>"
dns_nameservers:
  - 8.8.8.8
router_name: "<ROUTER_NAME>"
external_network_name: "<EXTERNAL_NET>"

# ─── Compute ──────────────────────────────────────────────────────────────────
vm_base_name: "<VM_BASE_NAME>"         # prefix; instances named <base>-01, -02, …
vm_count: 1
image_name: "<GLANCE_IMAGE_NAME>"
flavor_name: "<FLAVOR_NAME>"
keypair_name: ""                       # leave empty to omit keypair
availability_zone: ""                  # leave empty for Nova scheduler to decide
security_group_name: "<SG_NAME>"

# ─── Storage ──────────────────────────────────────────────────────────────────
boot_from_volume: false                # true = Cinder boot volume; false = ephemeral
volume_size_gb: 20
delete_volume_on_termination: true
volume_name: "<VOLUME_NAME>"
volume_type: "<VOLUME_TYPE>"           # e.g. ceph-ssd, lvm; omit for project default

# ─── Optional Flavor Creation ─────────────────────────────────────────────────
create_flavor: false
flavor_vcpus: 2
flavor_ram_mb: 4096
flavor_disk_gb: 20
flavor_is_public: true
flavor_extra_specs: {}

# ─── Image Upload ─────────────────────────────────────────────────────────────
image_upload_name: "<IMAGE_NAME>"
image_local_path: "<PATH_TO_IMAGE_FILE>"
image_disk_format: qcow2
image_container_format: bare
image_visibility: private
image_base_properties:
  hw_disk_bus: scsi
  hw_scsi_model: virtio-scsi
  hw_machine_type: q35
  hw_qemu_guest_agent: "yes"
  os_require_quiesce: "yes"
image_extra_properties: {}             # keys here override image_base_properties

# ─── Cloud-init ───────────────────────────────────────────────────────────────
cloud_init_enabled: false
cloud_init_user: "<OS_DEFAULT_USER>"   # e.g. ubuntu, rocky, cloud-user
cloud_init_password: ""                # leave empty for key-only auth
cloud_init_groups: []
cloud_init_ssh_keys: []
cloud_init_packages: []
cloud_init_write_files: []
cloud_init_runcmd: []
```

---

## Task Patterns

### `tasks/token.yml` — only for plays making raw `uri` calls

```yaml
---
- name: Get OpenStack auth token
  openstack.cloud.auth:
    cloud: "{{ cloud_name }}"
  register: _auth_result
  no_log: true

- name: Set keystone_token fact
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

Cross-play access: `hostvars['localhost']['keystone_token']`

### `tasks/network.yml`

> `provider_*` params require admin credentials. Verify `external` vs `is_router_external` for installed version.

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

### `tasks/router.yml`

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

### `tasks/security.yml`

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

### `tasks/compute.yml`

> Return key is `server` in openstack.cloud 2.x (was `openstack` in 1.x). Fixed IP: `_server.server.access_ipv4`.

**Single instance:**

```yaml
---
- name: Create instance
  openstack.cloud.server:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ instance_name }}"
    image: "{{ image_name }}"
    flavor: "{{ flavor_name }}"
    key_name: "{{ keypair_name | default(omit, true) }}"
    network: "{{ network_name }}"
    availability_zone: "{{ availability_zone | default(omit, true) }}"
    security_groups:
      - "{{ security_group_name }}"
    auto_ip: false
    wait: true
    timeout: 300
  register: _server

- name: Set instance IP fact
  ansible.builtin.set_fact:
    instance_ip: "{{ _server.server.access_ipv4 }}"
```

**Bulk instances with sequential naming, boot-from-volume, and cloud-init:**

```yaml
---
- name: Render cloud-init user-data
  ansible.builtin.set_fact:
    _userdata: "{{ lookup('ansible.builtin.template', playbook_dir + '/../templates/cloud-init.yml.j2') }}"
  when: cloud_init_enabled | bool

- name: Deploy VM instances
  openstack.cloud.server:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ vm_base_name }}-{{ '%02d' | format(item + 1) }}"
    image: "{{ image_name }}"
    flavor: "{{ flavor_name }}"
    key_name: "{{ keypair_name | default(omit, true) }}"
    network: "{{ network_name }}"
    availability_zone: "{{ availability_zone | default(omit, true) }}"
    boot_from_volume: "{{ boot_from_volume | bool }}"
    volume_size: "{{ volume_size_gb if boot_from_volume | bool else omit }}"
    terminate_volume: "{{ delete_volume_on_termination if boot_from_volume | bool else omit }}"
    userdata: "{{ _userdata | default(omit) }}"
    auto_ip: false
    wait: true
    timeout: 300
  loop: "{{ range(vm_count | int) | list }}"
  register: _servers

- name: Build deployed instances list
  ansible.builtin.set_fact:
    deployed_instances: >-
      {{ deployed_instances | default([]) +
         [{'name': item.server.name, 'ip': item.server.access_ipv4}] }}
  loop: "{{ _servers.results }}"
  loop_control:
    label: "{{ item.server.name }}"

- name: Report deployed instances
  ansible.builtin.debug:
    msg: "{{ item.name }} → {{ item.ip }}"
  loop: "{{ deployed_instances }}"
  loop_control:
    label: "{{ item.name }}"
```

### `tasks/storage.yml` — separately attached data volumes

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

### `tasks/flavor.yml`

```yaml
---
- name: Create Nova flavor
  openstack.cloud.compute_flavor:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ flavor_name }}"
    ram: "{{ flavor_ram_mb }}"
    vcpus: "{{ flavor_vcpus }}"
    disk: "{{ flavor_disk_gb }}"
    is_public: "{{ flavor_is_public | default(true) }}"
    extra_specs: "{{ flavor_extra_specs if flavor_extra_specs else omit }}"
  when: create_flavor | bool
  register: _flavor
```

### `tasks/image.yml`

> `image_base_properties | combine(image_extra_properties | default({}))` — keys in `image_extra_properties` win on collision.

```yaml
---
- name: Verify image file exists
  ansible.builtin.stat:
    path: "{{ image_local_path }}"
  register: _image_stat

- name: Fail if image file is missing
  ansible.builtin.fail:
    msg: "Image file not found: {{ image_local_path }}"
  when: not _image_stat.stat.exists

- name: Upload image to Glance
  openstack.cloud.image:
    cloud: "{{ cloud_name }}"
    state: present
    name: "{{ image_upload_name }}"
    filename: "{{ image_local_path }}"
    disk_format: "{{ image_disk_format }}"
    container_format: "{{ image_container_format | default('bare') }}"
    visibility: "{{ image_visibility }}"
    properties: "{{ image_base_properties | combine(image_extra_properties | default({})) }}"
    wait: true
  register: _glance_image

- name: Report uploaded image
  ansible.builtin.debug:
    msg: "Uploaded '{{ _glance_image.image.name }}' — ID: {{ _glance_image.image.id }}, status: {{ _glance_image.image.status }}"
```

### `tasks/floatingip.yml`

> Return: `_fip.floating_ip.floating_ip_address` — verify for installed version.

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

### `tasks/render_inventory.yml`

```yaml
---
- name: Render dynamic inventory
  ansible.builtin.template:
    src: "../templates/inventory.yml.j2"
    dest: "{{ playbook_dir }}/../inventory/hosts.yml"
    mode: "0644"
  delegate_to: localhost
```

### `templates/cloud-init.yml.j2`

Rendered via `lookup('ansible.builtin.template', ...)` into a `set_fact`, then passed as `userdata:`. All sections are conditional.

```jinja
#cloud-config
users:
  - name: {{ cloud_init_user }}
    shell: /bin/bash
    sudo: 'ALL=(ALL) NOPASSWD:ALL'
{% if cloud_init_groups | default([]) %}
    groups: {{ cloud_init_groups | join(', ') }}
{% endif %}
{% if cloud_init_ssh_keys | default([]) %}
    ssh_authorized_keys:
{% for key in cloud_init_ssh_keys %}
      - {{ key }}
{% endfor %}
{% endif %}
{% if cloud_init_password | default('') %}

chpasswd:
  list: |
    {{ cloud_init_user }}:{{ cloud_init_password }}
  expire: false

ssh_pwauth: true
{% endif %}
{% if cloud_init_packages | default([]) %}

packages:
{% for pkg in cloud_init_packages %}
  - {{ pkg }}
{% endfor %}
package_update: true
package_upgrade: false
{% endif %}
{% if cloud_init_write_files | default([]) %}

write_files:
{% for f in cloud_init_write_files %}
  - path: {{ f.path }}
    permissions: '{{ f.permissions | default("0644") }}'
{% if f.owner is defined %}
    owner: {{ f.owner }}
{% endif %}
    content: |
{{ f.content | indent(6, first=True) }}
{% endfor %}
{% endif %}
{% if cloud_init_runcmd | default([]) %}

runcmd:
{% for cmd in cloud_init_runcmd %}
  - {{ cmd }}
{% endfor %}
{% endif %}
```

### `templates/inventory.yml.j2`

```jinja
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

### Deploy (resource-only, no SSH to instances)

```yaml
---
# Usage:
#   ansible-playbook playbooks/deploy.yml
#   ansible-playbook playbooks/deploy.yml -e vm_count=3
#   ansible-playbook playbooks/deploy.yml -e boot_from_volume=true -e volume_size_gb=50
#   ansible-playbook playbooks/deploy.yml -e availability_zone="nova:compute01"

- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  collections:
    - openstack.cloud
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - ansible.builtin.import_tasks: ../tasks/network.yml
    - ansible.builtin.import_tasks: ../tasks/security.yml
    - ansible.builtin.import_tasks: ../tasks/compute.yml
    - ansible.builtin.import_tasks: ../tasks/render_inventory.yml
```

### Two-phase: resource creation + SSH config

```yaml
---
- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  collections:
    - openstack.cloud
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - ansible.builtin.import_tasks: ../tasks/network.yml
    - ansible.builtin.import_tasks: ../tasks/security.yml
    - ansible.builtin.import_tasks: ../tasks/compute.yml
    - ansible.builtin.import_tasks: ../tasks/floatingip.yml
    - ansible.builtin.import_tasks: ../tasks/render_inventory.yml

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

### Teardown

```yaml
---
# Usage:
#   ansible-playbook playbooks/teardown.yml
#   ansible-playbook playbooks/teardown.yml -e vm_count=3
#
# boot_from_volume + delete_volume_on_termination=true: Nova removes boot volume with server.
# delete_volume_on_termination=false: volumes survive — clean up manually:
#   openstack volume list --long | grep <vm_base_name>

- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  collections:
    - openstack.cloud
  vars_files:
    - ../vars/<ENV>-vars.yml
  tasks:
    - name: Delete VM instances
      openstack.cloud.server:
        cloud: "{{ cloud_name }}"
        state: absent
        name: "{{ vm_base_name }}-{{ '%02d' | format(item + 1) }}"
        wait: true
        timeout: 300
      loop: "{{ range(vm_count | int) | list }}"

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

---

## Variable Reference

Set-fact variables (not in vars file):

| Variable | Set by | Description |
|---|---|---|
| `keystone_token` | `tasks/token.yml` | Bearer token; access cross-play via `hostvars['localhost']['keystone_token']` |
| `deployed_instances` | bulk compute loop | List of `{name, ip}` dicts |
| `instance_ip` | single-instance compute task | Fixed IP of the instance |
| `floating_ip` | `tasks/floatingip.yml` | Floating IP address |

All other variables live in `vars/<env>-vars.yml` — see the Variables section for the full reference.
