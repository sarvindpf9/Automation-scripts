---
name: host-ansible-play
description: "Use this skill when the user asks to write, generate, scaffold, or fix Ansible playbooks for configuring generic Linux VMs, bare-metal hosts, or OS-level host settings: networking (netplan, bonding, VLAN), hostname, packages, files, mounts, LVM/disk partitioning, sysctl, services, users, SSH hardening, multipath, or preflight checks. Produces SSH-based host/bare-metal Ansible projects using FQCN modules, group_vars-driven configuration, safe placeholders, idempotent tasks, handlers, and validation steps."
---

# Host / Bare-Metal Ansible Play Skill

## Rules

- Ask only the single most-blocking unknown before producing output.
- Treat official Ansible documentation as the primary source of truth for playbook syntax, module parameters, return values, and deprecations. Prefer local `ansible-doc <fqcn>` when available; otherwise use docs.ansible.com.
- Never invent environment-specific values. Use placeholders such as `<HOSTNAME_OR_IP>`, `<SSH_USER>`, `<INTERFACE_NAME>`, `<CIDR>`, `<GATEWAY_IP>`, `<DISK_DEVICE>`, `<VG_NAME>`, `<LV_NAME>`, `<NFS_SERVER>`, `<MOUNT_PATH>`.
- Always use FQCN modules: `ansible.builtin.template`, `ansible.builtin.lineinfile`, `ansible.posix.sysctl`, `community.general.parted`, etc.
- Configure Linux VMs and bare-metal hosts over SSH. Do not use `connection: local` unless the user explicitly asks for localhost-only automation.
- Keep environment-specific values in `group_vars/all.yml`, group-specific var files, `host_vars/`, or inventory. Do not inline them in task files.
- Use explicit `become: true` for host configuration that writes system files or runs privileged commands.
- Prefer structured output over text scraping. For `iproute2`, use `ip -j ...` plus `from_json`; avoid fragile regex parsing.
- Avoid deprecated injected fact variables such as `ansible_default_ipv4`, `ansible_hostname`, or `ansible_distribution`. Use `ansible_facts["default_ipv4"]["gateway"]`, `ansible_facts["hostname"]`, `ansible_facts["distribution"]`, etc.
- Make optional host changes opt-in with empty defaults, e.g. `target_hostname: ""` and `when: target_hostname | length > 0`.
- Do not set `stdout_callback = yaml` unless the project also installs the callback dependency. Use `stdout_callback = default` for portable templates.
- Use `ansible.builtin.command` when no shell features are required. Use `ansible.builtin.shell` only for shell builtins, pipes, redirects, globbing, or compound expressions, and set `args.executable: /bin/bash` when Bash is required.
- For edits to critical files (`/etc/fstab`, `/etc/netplan/*.yaml`, service configs, SSH config, multipath config), set `backup: true`.
- For files, directories, templates, and line edits, set owner/group/mode explicitly.
- Validate derived facts with `ansible.builtin.assert` before writing critical config.
- When adding named config blocks to existing service configs, use `ansible.builtin.blockinfile` with a stable marker and add a preflight guard that fails if unmanaged blocks with the same runtime names already exist.
- For INI-style override files, prefer `community.general.ini_file` for individual keys instead of `blockinfile`; this avoids duplicate sections and updates existing keys idempotently.
- When rollback is requested for service config changes, remove only the managed block or managed keys and assert that the default/base config file still exists before proceeding.
- Apply disruptive changes through handlers where possible, e.g. render netplan then notify `netplan apply`, render service config then notify service restart.
- Keep generated tasks narrowly scoped to the user's requested operations. Do not add unrequested resources, hardening, users, storage, or network changes.
- Prefer simple task files over premature roles for small one-off host plays. Create roles only when the user asks for reusable role structure or the project already uses roles.
- Add non-builtin collections only when a requested module requires them, and include `requirements.yml` only in that case.

---

## Official Documentation First

Before emitting or changing module parameters for non-trivial tasks, verify against official Ansible documentation:

```bash
ansible-doc ansible.builtin.<module>
ansible-doc ansible.posix.<module>
ansible-doc community.general.<module>
ansible-doc -l | grep <keyword>
```

If `ansible-doc` is unavailable or the installed version is not representative of the target environment, use the official Ansible docs at `https://docs.ansible.com/`. Do not rely on examples from blogs, old Stack Overflow answers, or deprecated variable styles when official docs are available.

Common references:

| Topic | Official source |
| ---- | --------------- |
| Playbook syntax | https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_intro.html |
| Builtin modules | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/ |
| `ansible.builtin.hostname` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/hostname_module.html |
| `ansible.builtin.template` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/template_module.html |
| `ansible.builtin.lineinfile` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/lineinfile_module.html |
| `ansible.builtin.command` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/command_module.html |
| `ansible.builtin.shell` | https://docs.ansible.com/ansible/latest/collections/ansible/builtin/shell_module.html |
| Facts and magic variables | https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_vars_facts.html |

When the user's target Ansible version is known, match that version's official documentation or local `ansible-doc` output.

---

## Directory Layout

Use this layout for new generic host/bare-metal playbooks:

```text
<nn>-<slug>/
├── ansible.cfg
├── requirements.txt
├── requirements.yml                 # only when non-builtin collections are required
├── inventory.yaml
├── group_vars/
│   ├── all.yml                      # shared defaults
│   ├── baremetal.yml                # only when bare-metal-specific values are needed
│   └── vms.yml                      # only when VM-specific values are needed
├── host_vars/                       # only when per-host values are needed
├── playbooks/
│   └── <operation>.yml              # entry point
├── tasks/                           # imported task files only
└── templates/                       # only when rendering config files
```

`playbooks/<operation>.yml` is the entry point. Task files under `tasks/` are imported, not run directly.

---

## Standard Files

### `ansible.cfg`

```ini
[defaults]
inventory = inventory.yaml
host_key_checking = False
retry_files_enabled = False
stdout_callback = default
gathering = smart

[privilege_escalation]
become = True
become_method = sudo

[ssh_connection]
pipelining = True
```

### `requirements.txt`

```text
ansible-core>=2.14
ansible-lint>=6.0
```

### `requirements.yml`

Include this file only when the generated playbook uses modules outside `ansible.builtin`.

```yaml
---
collections:
  - name: ansible.posix
    version: ">=1.5"
  - name: community.general
    version: ">=8.0"
```

Install collections with:

```bash
ansible-galaxy collection install -r requirements.yml
```

### `inventory.yaml`

```yaml
---
all:
  children:
    target_hosts:
      hosts:
        host-1:
          ansible_host: <HOSTNAME_OR_IP>
          ansible_user: <SSH_USER>
```

Use `baremetal` and `vms` inventory groups only when the requested playbook needs different behavior for those host types. Do not place passwords, private keys, or customer-specific IPs in committed sample inventory. Use placeholders.

### `group_vars/all.yml`

```yaml
---
# Optional hostname. Leave empty to keep the current hostname.
target_hostname: ""

# Example network override values. Leave empty to auto-detect where supported.
internet_probe_ip: "1.1.1.1"
internet_interface_name: ""
internet_interface_cidr: ""
internet_gateway: ""
dns_servers: []

# Optional storage, package, service, sysctl, and user inputs.
required_commands: []
fstab_entries: []              # list of {src, path, line}
lvm_volume_groups: []
required_packages: []
managed_services: []
sysctl_settings: {}
managed_users: []
```

Keep defaults empty unless a value is a safe tool default rather than an environment-specific value.

---

## Playbook Pattern

```yaml
---
- name: Configure Linux hosts
  hosts: target_hosts
  gather_facts: true
  become: true

  handlers:
    - name: Apply netplan
      ansible.builtin.command: netplan apply

    - name: Reload systemd
      ansible.builtin.systemd:
        daemon_reload: true

    - name: Restart service
      ansible.builtin.service:
        name: "{{ service_name }}"
        state: restarted

  tasks:
    - name: Run preflight checks
      ansible.builtin.import_tasks: ../tasks/preflight.yml

    - name: Configure requested hostname
      ansible.builtin.import_tasks: ../tasks/hostname.yml
      when: target_hostname | length > 0
```

Import only task files relevant to the requested operation. Do not include storage, SSH hardening, users, or network tasks unless the user asked for them.

---

## Task Patterns

### `tasks/preflight.yml`

```yaml
---
- name: Assert supported Linux distribution
  ansible.builtin.assert:
    that:
      - ansible_facts["distribution"] in ["Ubuntu", "Debian", "Rocky", "RedHat", "CentOS", "AlmaLinux"]
    fail_msg: "Unsupported OS: {{ ansible_facts['distribution'] }}"

- name: Verify required commands are present
  ansible.builtin.shell: "command -v {{ item }}"
  args:
    executable: /bin/bash
  changed_when: false
  loop: "{{ required_commands }}"
  when: required_commands | length > 0
```

Set `required_commands` from `group_vars/all.yml` or directly in the play for commands needed by the requested task. Use `ansible.builtin.shell` here because `command -v` is a shell builtin.

### Existing Service Config Blocks

Use this pattern when appending a named frontend/backend/listener/stanza to an existing config such as HAProxy, Nginx, SSH, or application service configs:

- Save a one-time remote copy before the first managed edit when rollback is expected: `copy` with `remote_src: true` and `force: false`.
- Read the file with `slurp` only after `stat` confirms it exists.
- Fail before writing if an unmanaged block with the same runtime name already exists. Do not silently append a second block that creates duplicate service config.
- Use one stable `blockinfile` marker per managed feature so reruns update the same block instead of appending another copy.
- On rollback, use `blockinfile: state: absent` with the same marker and assert the base config file still exists.

```yaml
---
- name: Check service configuration file
  ansible.builtin.stat:
    path: "{{ service_config_path }}"
  register: service_config

- name: Save one-time service configuration rollback copy
  ansible.builtin.copy:
    src: "{{ service_config_path }}"
    dest: "{{ service_config_backup_path }}"
    remote_src: true
    force: false
    owner: root
    group: root
    mode: "0644"
  when: service_config.stat.exists

- name: Read existing service configuration
  ansible.builtin.slurp:
    path: "{{ service_config_path }}"
  register: service_config_content
  when: service_config.stat.exists

- name: Prevent duplicate unmanaged service section
  ansible.builtin.assert:
    that:
      - >-
        managed_section_count == 0
        or (
          managed_section_count == 1
          and '# BEGIN ANSIBLE MANAGED EXAMPLE SECTION' in service_config_text
        )
    fail_msg: >-
      Existing unmanaged section {{ managed_section_name }} was found in
      {{ service_config_path }}. Remove or rename it before running this play.
  vars:
    service_config_text: "{{ service_config_content.content | b64decode }}"
    managed_section_count: >-
      {{
        service_config_text
        | regex_findall('(?m)^frontend\\s+' ~ managed_section_name ~ '\\s*$')
        | length
      }}
  when: service_config.stat.exists

- name: Add managed service config block
  ansible.builtin.blockinfile:
    path: "{{ service_config_path }}"
    marker: "# {mark} ANSIBLE MANAGED EXAMPLE SECTION"
    insertafter: EOF
    owner: root
    group: root
    mode: "0644"
    backup: true
    block: |
      frontend {{ managed_section_name }}
              mode http
  notify: Restart service
  when: service_config.stat.exists
```

Rollback counterpart:

```yaml
---
- name: Check service configuration file
  ansible.builtin.stat:
    path: "{{ service_config_path }}"
  register: service_config

- name: Ensure base service configuration file exists
  ansible.builtin.assert:
    that:
      - service_config.stat.exists
      - service_config.stat.isreg
    fail_msg: "{{ service_config_path }} must exist before rollback proceeds."

- name: Remove managed service config block
  ansible.builtin.blockinfile:
    path: "{{ service_config_path }}"
    marker: "# {mark} ANSIBLE MANAGED EXAMPLE SECTION"
    state: absent
    owner: root
    group: root
    mode: "0644"
    backup: true
  notify: Restart service
```

### INI Override Files

Use `community.general.ini_file` for INI-style files so existing keys are updated and duplicate sections are not appended. Include `community.general` in `requirements.yml` when using this module.

```yaml
---
- name: Set service endpoint override
  community.general.ini_file:
    path: "{{ service_override_path }}"
    section: glance
    option: endpoint_override
    value: "{{ service_endpoint_override }}"
    create: true
    owner: root
    group: root
    mode: "0644"
    backup: true
    exclusive: true
  notify: Restart service

- name: Remove service endpoint override
  community.general.ini_file:
    path: "{{ service_override_path }}"
    section: glance
    option: endpoint_override
    state: absent
    owner: root
    group: root
    mode: "0644"
    backup: true
  notify: Restart service
  when: service_override_file.stat.exists
```

### Hostname

```yaml
---
- name: Apply requested hostname
  ansible.builtin.hostname:
    name: "{{ target_hostname }}"
  when: target_hostname | length > 0

- name: Update /etc/hosts loopback entry
  ansible.builtin.lineinfile:
    path: /etc/hosts
    regexp: '^127\.0\.1\.1'
    line: "127.0.1.1 {{ target_hostname }}"
    owner: root
    group: root
    mode: "0644"
    backup: true
  when: target_hostname | length > 0
```

### Netplan

- Detect interface data with `ip -j` and `from_json`.
- Use `ansible_facts["default_ipv4"]["gateway"]` for the default gateway fallback; do not use deprecated injected facts such as `ansible_default_ipv4.gateway`.
- Render `/etc/netplan/<file>.yaml` from a Jinja2 template.
- Set `mode: "0600"` and `backup: true`.
- Notify a handler that runs `netplan apply`.
- Validate that interface, CIDR, gateway, DNS, VLAN, bond, and secondary interface values are non-empty before writing when those values are required.
- If the user provides an exact required shape, preserve that shape in the template.

```yaml
---
- name: Detect route used for internet probe
  ansible.builtin.command: "ip -j -4 route get {{ internet_probe_ip }}"
  register: internet_route
  changed_when: false
  when: >
    internet_interface_name | length == 0
    or internet_interface_cidr | length == 0

- name: Parse detected route
  ansible.builtin.set_fact:
    detected_route: "{{ (internet_route.stdout | from_json)[0] }}"
  when: internet_route is not skipped

- name: Set resolved interface and gateway
  ansible.builtin.set_fact:
    resolved_interface: >-
      {{
        internet_interface_name
        if internet_interface_name | length > 0
        else detected_route.dev
      }}
    resolved_gateway: >-
      {{
        internet_gateway
        if internet_gateway | length > 0
        else ansible_facts["default_ipv4"]["gateway"] | default("")
      }}

- name: Assert required network values are known
  ansible.builtin.assert:
    that:
      - resolved_interface | length > 0
      - resolved_gateway | length > 0
      - internet_interface_cidr | length > 0
    fail_msg: "Set internet_interface_name, internet_interface_cidr, and internet_gateway when auto-detection is insufficient."

- name: Render netplan config
  ansible.builtin.template:
    src: netplan.yaml.j2
    dest: /etc/netplan/99-managed.yaml
    owner: root
    group: root
    mode: "0600"
    backup: true
  notify: Apply netplan
```

### Network Bonding / LACP

Use a group var such as:

```yaml
---
bond_interfaces:
  - name: bond0
    mode: 802.3ad
    members:
      - <MEMBER_IFACE_1>
      - <MEMBER_IFACE_2>
    cidr: <CIDR>
    gateway: <GATEWAY_IP>
    mtu: 9000
```

Render bond config through a template that loops over `bond_interfaces`. Do not assume LACP support; if the user does not specify bond mode, ask or use a placeholder.

### Fstab

Use `ansible.builtin.lineinfile` for a small fixed set of entries:

```yaml
---
- name: Ensure mount directories exist
  ansible.builtin.file:
    path: "{{ item.path }}"
    state: directory
    owner: root
    group: root
    mode: "0755"
  loop: "{{ fstab_entries }}"
  loop_control:
    label: "{{ item.path }}"

- name: Add mount entries to fstab
  ansible.builtin.lineinfile:
    path: /etc/fstab
    regexp: >-
      ^{{ item.src | regex_escape }}\s+{{ item.path | regex_escape }}\s+
    line: "{{ item.line }}"
    owner: root
    group: root
    mode: "0644"
    create: false
    backup: true
  loop: "{{ fstab_entries }}"
  loop_control:
    label: "{{ item.path }}"
```

Create mount directories before editing `/etc/fstab`. Do not run `mount -a` unless the user explicitly asks for immediate mounting.

### LVM And Filesystems

Use `community.general.parted`, `community.general.lvg`, `community.general.lvol`, and `community.general.filesystem` only when disk or LVM work is requested. Require explicit device placeholders or user-provided values; never infer a write target from `lsblk`.

For disks whose first partition is not formed by appending `1` to the device path, such as many NVMe devices, require `partition_device` in vars.

```yaml
---
- name: Assert LVM inputs are explicit
  ansible.builtin.assert:
    that:
      - item.device is match('^/dev/')
      - item.vg_name | length > 0
      - item.lvols | length > 0
    fail_msg: "Each LVM volume group requires device, vg_name, and lvols."
  loop: "{{ lvm_volume_groups }}"
  loop_control:
    label: "{{ item.vg_name | default(item.device) }}"

- name: Create GPT partition
  community.general.parted:
    device: "{{ item.device }}"
    label: gpt
    number: 1
    state: present
    part_end: "100%"
  loop: "{{ lvm_volume_groups }}"
  loop_control:
    label: "{{ item.device }}"

- name: Create volume group
  community.general.lvg:
    vg: "{{ item.vg_name }}"
    pvs: "{{ item.partition_device | default(item.device ~ '1') }}"
    state: present
  loop: "{{ lvm_volume_groups }}"
  loop_control:
    label: "{{ item.vg_name }}"

- name: Create logical volumes
  community.general.lvol:
    vg: "{{ item.0.vg_name }}"
    lv: "{{ item.1.lv_name }}"
    size: "{{ item.1.size }}"
    state: present
  loop: "{{ lvm_volume_groups | subelements('lvols') }}"
  loop_control:
    label: "{{ item.1.lv_name }}"

- name: Create filesystems
  community.general.filesystem:
    fstype: "{{ item.1.fstype | default('xfs') }}"
    dev: "/dev/{{ item.0.vg_name }}/{{ item.1.lv_name }}"
  loop: "{{ lvm_volume_groups | subelements('lvols') }}"
  loop_control:
    label: "{{ item.1.lv_name }}"
```

Schema example:

```yaml
---
lvm_volume_groups:
  - device: /dev/<DISK_DEVICE>
    partition_device: /dev/<PARTITION_DEVICE>
    vg_name: <VG_NAME>
    lvols:
      - lv_name: <LV_NAME>
        size: 100%FREE
        fstype: xfs
```

### Packages And Services

```yaml
---
- name: Install required packages
  ansible.builtin.package:
    name: "{{ required_packages }}"
    state: present
  when: required_packages | length > 0

- name: Ensure managed services are enabled and started
  ansible.builtin.service:
    name: "{{ item }}"
    enabled: true
    state: started
  loop: "{{ managed_services }}"
```

Use generic `ansible.builtin.package` unless the user specifies an OS family or package-manager-specific behavior.

### Sysctl

```yaml
---
- name: Apply sysctl settings
  ansible.posix.sysctl:
    name: "{{ item.key }}"
    value: "{{ item.value }}"
    state: present
    reload: true
    sysctl_set: true
  loop: "{{ sysctl_settings | dict2items }}"
  loop_control:
    label: "{{ item.key }}"
```

Do not add tuning values unless the user supplied them or requested a named tuning profile.

### Users And SSH Keys

```yaml
---
- name: Ensure managed users exist
  ansible.builtin.user:
    name: "{{ item.name }}"
    groups: "{{ item.groups | default([]) }}"
    append: true
    shell: "{{ item.shell | default('/bin/bash') }}"
    state: present
  loop: "{{ managed_users }}"
  loop_control:
    label: "{{ item.name }}"

- name: Authorize SSH keys
  ansible.posix.authorized_key:
    user: "{{ item.name }}"
    key: "{{ item.key }}"
    state: present
    exclusive: false
  loop: "{{ managed_users }}"
  when: item.key is defined and item.key | length > 0
  loop_control:
    label: "{{ item.name }}"
```

### SSH Hardening

Use SSH hardening only when explicitly requested. Prefer a variable-driven map rather than fixed policy baked into the task file:

```yaml
---
- name: Apply sshd configuration settings
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "^#?{{ item.key }}\\s+"
    line: "{{ item.key }} {{ item.value }}"
    owner: root
    group: root
    mode: "0600"
    backup: true
    validate: "sshd -t -f %s"
  loop: "{{ sshd_settings | dict2items }}"
  loop_control:
    label: "{{ item.key }}"
  notify: Restart sshd
```

`group_vars` example:

```yaml
sshd_settings:
  PermitRootLogin: "no"
  PasswordAuthentication: "no"
  X11Forwarding: "no"
  MaxAuthTries: "3"
```

### Files And Templates

```yaml
---
- name: Render managed config
  ansible.builtin.template:
    src: config.j2
    dest: "{{ config_path }}"
    owner: root
    group: root
    mode: "0644"
    backup: true
  notify: Restart service
```

Use `validate` for configuration files when the target daemon provides a syntax-check command.

### Multipath

Install and enable `multipathd` via packages/services tasks. For iSCSI/FC multipath:

```yaml
---
- name: Configure multipath
  ansible.builtin.template:
    src: multipath.conf.j2
    dest: /etc/multipath.conf
    owner: root
    group: root
    mode: "0644"
    backup: true
  notify: Restart multipathd
```

Do not generate a `multipath.conf` unless the user provides the WWID, alias list, or exact template shape.

---

## Validation

Run local validation after generating or changing playbooks:

```bash
yamllint inventory.yaml group_vars/ playbooks/*.yml
ANSIBLE_LOCAL_TEMP="$(pwd)/.ansible/tmp" ansible-playbook --syntax-check playbooks/<operation>.yml
ansible-lint playbooks/<operation>.yml
```

If Ansible cannot write to the default user temp path in the sandbox, create `.ansible/tmp` inside the project and set `ANSIBLE_LOCAL_TEMP` for syntax checks. Remove temporary validation directories before finishing.

Do not claim a remote playbook run succeeded unless it was actually executed against the target hosts.

---

## README Guidance

When generating a README for a host/bare-metal Ansible project, use the repository `readme-writer` skill. Document:

- Entry-point playbook.
- Local and remote dependencies.
- Required collections.
- Variables from `group_vars/all.yml`, group-specific var files, and `host_vars/`.
- Inventory placeholders and sensitive-data warning.
- What files are changed on the target.
- Pre-checks and failure behavior.
- Verification commands.
