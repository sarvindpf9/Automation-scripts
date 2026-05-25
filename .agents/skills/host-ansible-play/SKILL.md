---
name: host-ansible-play
description: "Use this skill when the user asks to write, generate, scaffold, or fix Ansible playbooks for configuring generic Linux VMs, bare-metal hosts, or OS-level host settings such as networking, hostname, packages, files, mounts, services, users, sysctl, storage mounts, or preflight checks. Produces SSH-based host/bare-metal Ansible projects using FQCN modules, group_vars-driven configuration, safe placeholders, idempotent tasks, and validation steps."
---

# Host Ansible Play Skill

## Rules

- Ask only the single most-blocking unknown before producing output.
- Treat official Ansible documentation as the primary source of truth for playbook syntax, module parameters, return values, and deprecations. Prefer local `ansible-doc ansible.builtin.<module>` when available; otherwise use docs.ansible.com.
- Never invent environment-specific values. Use placeholders such as `<HOSTNAME_OR_IP>`, `<SSH_USER>`, `<INTERFACE_NAME>`, `<CIDR>`, `<GATEWAY_IP>`, `<NFS_SERVER>`, `<MOUNT_PATH>`.
- Always use FQCN modules: `ansible.builtin.template`, `ansible.builtin.lineinfile`, `ansible.builtin.hostname`, etc.
- Configure Linux VMs/bare-metal over SSH. Do not use `connection: local` unless the user explicitly asks for localhost-only automation.
- Keep environment-specific values in `group_vars/all.yml`, `host_vars/`, or inventory. Do not inline them in task files.
- Use explicit `become: true` for host configuration that writes system files or runs privileged commands.
- Prefer structured output over text scraping. For `iproute2`, use `ip -j ...` plus `from_json`; avoid fragile `regex_search(..., '\\1') | first` patterns.
- Avoid deprecated injected fact variables such as `ansible_default_ipv4`, `ansible_hostname`, or `ansible_distribution`. Use `ansible_facts["default_ipv4"]["gateway"]`, `ansible_facts["hostname"]`, `ansible_facts["distribution"]`, etc.
- Make optional host changes opt-in with empty defaults, e.g. `target_hostname: ""` and `when: target_hostname | length > 0`.
- Do not set `stdout_callback = yaml` unless the project also installs the callback dependency. Use `stdout_callback = default` for portable templates.
- Use `ansible.builtin.command` when no shell features are required. Use `ansible.builtin.shell` only for shell builtins, pipes, redirects, or compound expressions, and set `args.executable: /bin/bash` when Bash is required.
- For edits to critical files (`/etc/fstab`, `/etc/netplan/*.yaml`, service configs), set `backup: true`.
- For files, directories, templates, and line edits, set owner/group/mode explicitly.
- Validate derived facts with `ansible.builtin.assert` before writing critical config.
- Apply disruptive changes through handlers where possible, e.g. render netplan then notify `netplan apply`, render service config then notify service restart.
- Keep generated tasks narrowly scoped to the user's requested operations.

---

## Official Documentation First

Before emitting or changing module parameters for non-trivial tasks, verify against official Ansible documentation:

```bash
ansible-doc ansible.builtin.<module>
ansible-doc -l ansible.builtin | grep <keyword>
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

```
<nn>-<slug>/
├── ansible.cfg
├── requirements.txt
├── requirements.yml                 # only when collections are required
├── inventory.yaml
├── group_vars/
│   └── all.yml
├── host_vars/                       # only when per-host values are needed
├── playbooks/
│   └── <operation>.yml
├── tasks/                           # optional; use for shared/imported tasks
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

[privilege_escalation]
become = True
become_method = sudo
```

### `requirements.txt`

```text
ansible-core>=2.14
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

Do not place passwords, private keys, or customer-specific IPs in committed sample inventory. Use placeholders.

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
```

---

## Playbook Pattern

```yaml
---
- name: Configure Linux hosts
  hosts: target_hosts
  gather_facts: true
  become: true

  tasks:
    - name: Apply requested hostname
      ansible.builtin.hostname:
        name: "{{ target_hostname }}"
      when: target_hostname | length > 0

    - name: Ensure required commands are present
      ansible.builtin.shell: "command -v {{ item }}"
      args:
        executable: /bin/bash
      changed_when: false
      loop:
        - ip

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
      when: >
        internet_interface_name | length == 0
        or internet_interface_cidr | length == 0

    - name: Set internet interface
      ansible.builtin.set_fact:
        detected_interface: >-
          {{
            internet_interface_name
            if internet_interface_name | length > 0
            else detected_route.dev
          }}

    - name: Set internet gateway
      ansible.builtin.set_fact:
        detected_gateway: >-
          {{
            internet_gateway
            if internet_gateway | length > 0
            else ansible_facts["default_ipv4"]["gateway"]
          }}
```

Use the pattern above only when the requested playbook needs routed-interface detection. Otherwise omit it.

---

## Common Task Patterns

### Hostname

```yaml
- name: Apply requested hostname
  ansible.builtin.hostname:
    name: "{{ target_hostname }}"
  when: target_hostname | length > 0
```

### Netplan

- Detect interface data with `ip -j` and `from_json`.
- Use `ansible_facts["default_ipv4"]["gateway"]` for the default gateway fallback; do not use deprecated injected facts such as `ansible_default_ipv4.gateway`.
- Render `/etc/netplan/<file>.yaml` from a Jinja2 template.
- Set `mode: "0600"` and `backup: true`.
- Notify a handler that runs `netplan apply`.
- Validate that interface, CIDR, gateway, and secondary interface values are non-empty before writing.
- If the user provides an exact required shape, preserve that shape in the template.

### Fstab

Use `ansible.builtin.lineinfile` for a small fixed set of entries:

```yaml
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
```

Create mount directories before editing `/etc/fstab`. Do not run `mount -a` unless the user explicitly asks for immediate mounting.

### Packages And Services

```yaml
- name: Install required packages
  ansible.builtin.package:
    name: "{{ required_packages }}"
    state: present

- name: Ensure service is enabled and started
  ansible.builtin.service:
    name: "{{ service_name }}"
    enabled: true
    state: started
```

Use generic `ansible.builtin.package` unless the user specifies an OS family or package manager.

### Files And Templates

```yaml
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

---

## Validation

Run local validation after generating or changing playbooks:

```bash
yamllint inventory.yaml group_vars/all.yml playbooks/*.yml
ANSIBLE_LOCAL_TEMP="$(pwd)/.ansible/tmp" ansible-playbook --syntax-check playbooks/<operation>.yml
```

If Ansible cannot write to the default user temp path in the sandbox, create `.ansible/tmp` inside the project and set `ANSIBLE_LOCAL_TEMP` for syntax checks. Remove temporary validation directories before finishing.

Do not claim a remote playbook run succeeded unless it was actually executed against the target hosts.

---

## README Guidance

When generating a README for a host/bare-metal Ansible project, use the repository `readme-writer` skill. Document:

- Entry-point playbook.
- Local and remote dependencies.
- Variables from `group_vars/all.yml` and `host_vars/`.
- Inventory placeholders and sensitive-data warning.
- What files are changed on the target.
- Pre-checks and failure behavior.
- Verification commands.
