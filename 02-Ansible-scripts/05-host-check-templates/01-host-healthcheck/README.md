# 01-host-healthcheck

Ansible playbook that audits Linux host health by verifying configurable kernel (sysctl) parameters and NTP synchronisation status, reporting per-host `OK`/`WARN` results without modifying any state on the target.

---

## `playbooks/healthcheck.yml`

Entry-point playbook that imports `tasks/check_sysctl.yml` and `tasks/check_ntp.yml` against all hosts in the `target_hosts` inventory group. All tasks are read-only — no configuration is changed on the target.

**Dependencies (local):**

- `ansible-core >= 2.14` — Ansible engine; install via `pip install -r requirements.txt`
- `ansible-lint >= 6.0` — optional linting; included in `requirements.txt`
- SSH access to each target host (password or key-based — see [Inventory configuration](#inventory--inventoryyaml))

**Dependencies (remote hosts):**

- `sysctl` — reads kernel parameters; present on all standard Linux distributions
- `timedatectl` — queries NTP status; requires a systemd-based OS (Ubuntu 18.04+, RHEL 7+, Debian 9+)
- `sudo` — all tasks run with `become: true`; the SSH user must have passwordless `sudo` or `NOPASSWD` for the commands invoked

**What it does:**

1. Connects to each host in `target_hosts` using credentials from `inventory.yaml`
2. Gathers host facts (hostname is used in all report messages)
3. Reads each sysctl parameter listed in `group_vars/all.yml` via `sysctl -n` and emits `hostname | param = value`
4. Runs `timedatectl status` and parses the `NTP service` and `System clock synchronized` fields
5. Reports per-host NTP state: `hostname | ntp_service=active | clock_synced=True | status=OK`
6. Emits an additional `WARNING` debug message for any host where the NTP service is inactive or the clock is not synchronised

### Usage

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run health checks against all hosts in target_hosts
ansible-playbook playbooks/healthcheck.yml

# Limit the run to a single host
ansible-playbook playbooks/healthcheck.yml --limit host-1

# Verify connectivity before running checks
ansible target_hosts -m ansible.builtin.ping
```

### Inventory — `inventory.yaml`

> **Sensitive data:** `ansible_host`, `ansible_user`, and `ansible_password` hold credentials.
> Replace the placeholders below with real values. **Do not commit live credentials to version control** — use Ansible Vault or an external secrets manager.

Edit `inventory.yaml` to reflect your environment:

```yaml
all:
  children:
    target_hosts:
      hosts:
        host-1:
          ansible_host: <HOSTNAME_OR_IP>    # target host IP or FQDN
          ansible_user: <SSH_USER>           # SSH login username
          ansible_password: <SSH_PASSWORD>   # SSH password
```

To add more hosts, append entries under `target_hosts` following the same structure.
To use key-based authentication instead, replace `ansible_password` with:

```yaml
ansible_ssh_private_key_file: <PATH_TO_PRIVATE_KEY>
```

### sysctl parameters — `group_vars/all.yml`

Extend `sysctl_check_params` with any parameter readable by `sysctl -n`. The full list is checked against every host in the inventory.

```yaml
sysctl_check_params:
  - net.ipv4.tcp_retries2
  - net.core.somaxconn      # example additional parameter
```

### Example outputs

Healthy host — sysctl and NTP both passing:

```
TASK [Report sysctl parameter values] ******************************************
ok: [host-1] => (item=net.ipv4.tcp_retries2) => {
    "msg": "host-1 | net.ipv4.tcp_retries2 = 15"
}

TASK [Report NTP status] *******************************************************
ok: [host-1] => {
    "msg": "host-1 | ntp_service=active | clock_synced=True | status=OK"
}
```

Host with NTP not synchronised:

```
TASK [Report NTP status] *******************************************************
ok: [host-2] => {
    "msg": "host-2 | ntp_service=inactive | clock_synced=False | status=WARN"
}

TASK [Warn if NTP is not fully synchronised] ***********************************
ok: [host-2] => {
    "msg": "WARNING: host-2 NTP not fully synchronised (ntp_service=inactive, clock_synced=False)"
}
```

### Compatibility

| Check | Requirement |
| ----- | ----------- |
| `check_sysctl.yml` | Any Linux with `sysctl` (all major distributions) |
| `check_ntp.yml` | systemd-based OS with `timedatectl` (Ubuntu 18.04+, RHEL/CentOS 7+, Debian 9+) |

The NTP check will fail on non-systemd targets (e.g., containers with no init, Alpine with OpenRC) because `timedatectl` is not available on those systems.

### Extending checks

Each check is a self-contained task file under `tasks/`. To add a new check:

1. Create `tasks/check_<topic>.yml` following the pattern of the existing files.
2. Import it in `playbooks/healthcheck.yml`:

```yaml
- name: Check <topic>
  ansible.builtin.import_tasks: ../tasks/check_<topic>.yml
```

If the new check requires configurable parameters, add them to `group_vars/all.yml` and reference them with `{{ variable_name }}` in the task file.
