# 04-glance-isolated-cluster

Ansible playbook resources for configuring local Glance access on Platform9 hosts that are running `pf9-glance-api`.

---

## `configure-glance-isolated-cluster.yml`

Configures HAProxy, Cinder, and Nova overrides for a Glance isolated cluster host. The playbook only applies changes when `pf9-glance-api.service` is installed as a loaded unit with an existing unit/source file and is active.

**Dependencies (local):**

- `ansible-core>=2.14` — required to run the playbook.
- `ansible-lint>=6.0` — optional linting dependency from `requirements.txt`.
- `community.general>=8.0` — required for idempotent INI key management through `community.general.ini_file`.
- SSH access to each host in the `glance_isolated_cluster_hosts` inventory group.
- A sudo-capable remote user set through `inventory.yaml`.

**Dependencies (remote host):**

- `pf9-glance-api.service` installed and visible through `systemctl show`.
- `/etc/haproxy/haproxy.cfg` must already exist for the HAProxy block to be appended.
- HAProxy must be installed and managed by the `haproxy` service.
- `/etc/ssl/private/glance-haproxy.pem` must exist before HAProxy can successfully restart.
- Platform9 service units `pf9-ostackhost.service` and `pf9-cindervolume-base` must exist if Nova or Cinder override files are changed.
- Sudo access for editing `/etc/haproxy/haproxy.cfg`, writing files under `/opt/pf9/etc`, and restarting services.

**What it does:**

1. Collects service facts from each target host.
2. Checks `systemctl show pf9-glance-api.service` for `LoadState=loaded`.
3. Verifies that the reported `FragmentPath` or `SourcePath` exists on disk.
4. Checks whether `systemctl is-active pf9-glance-api.service` returns `active`.
5. Falls back to service facts and checks whether `pf9-glance-api.service` or `pf9-glance-api` is in a `running` state.
6. Ends the current host when `pf9-glance-api.service` is not both installed and active, then continues with the remaining hosts.
7. Checks whether `glance_haproxy_cfg_path` exists.
8. Saves a one-time copy of the HAProxy config to `glance_haproxy_backup_path` before editing HAProxy.
9. Fails before editing HAProxy if unmanaged `glance_admin_local` or `glance_admin_cluster_local_https` sections already exist.
10. Appends or updates one Ansible-managed HAProxy block when the HAProxy config exists.
11. Configures `/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf` with idempotent INI key updates.
12. Configures `/opt/pf9/etc/nova/conf.d/nova_override.conf` with idempotent INI key updates.
13. Restarts `haproxy`, `pf9-cindervolume-base`, and `pf9-ostackhost.service` only when their managed files change.

### Usage

```bash
# Install local Ansible dependencies
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml

# Run against hosts from inventory.yaml
ansible-playbook playbooks/configure-glance-isolated-cluster.yml
```

```bash
# Override the allowed source subnet and Glance backend at runtime
ansible-playbook playbooks/configure-glance-isolated-cluster.yml \
  -e 'glance_haproxy_backend_servers=[{"name":"glance01","address":"10.96.13.51","port":9494}]'
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `glance_haproxy_cfg_path` | No | HAProxy config path checked before appending the managed Glance frontend and backend block. Default in `group_vars/all.yml` is `/etc/haproxy/haproxy.cfg`. |
| `glance_haproxy_backup_path` | No | One-time remote copy of the HAProxy config saved before the managed block is added. Default in `group_vars/all.yml` is `/etc/haproxy/haproxy.cfg.pre_glance_isolated_cluster`. |
| `glance_allowed_local_src` | No | Retained for compatibility with earlier versions of this playbook. The current HAProxy block does not render an ACL. |
| `glance_haproxy_backend_servers` | Yes | List of local Glance API backend servers rendered into the HAProxy backend. Each item contains `name`, `address`, and `port`. |
| `glance_endpoint_override` | No | Endpoint written to the Cinder and Nova override files. Default in `group_vars/all.yml` is `https://localhost:9494`. |
| `glance_cluster_enabled` | No | Value written as `glance_cluster` under `[pf9_glance]`. Default in `group_vars/all.yml` is `false`. |

### Examples

```bash
# Run with values defined in inventory.yaml and group_vars/all.yml
ansible-playbook playbooks/configure-glance-isolated-cluster.yml
```

```bash
# Run with two local Glance API backends
ansible-playbook playbooks/configure-glance-isolated-cluster.yml \
  -e 'glance_haproxy_backend_servers=[{"name":"glance01","address":"10.96.13.51","port":9494},{"name":"glance02","address":"10.96.13.208","port":9494}]'
```

### Inventory

`inventory.yaml` defines the `glance_isolated_cluster_hosts` group:

```yaml
---
all:
  children:
    glance_isolated_cluster_hosts:
      hosts:
        glance-host-1:
          ansible_host: <HOSTNAME_OR_IP>
          ansible_user: <SSH_USER>
```

Replace `<HOSTNAME_OR_IP>` and `<SSH_USER>` with environment-specific values before execution.

### Managed HAProxy block

The playbook appends an Ansible-managed block to `glance_haproxy_cfg_path`. The frontend listens on `9444` and forwards to backend servers from `glance_haproxy_backend_servers`.

Before the managed block is written, the playbook saves a non-overwriting copy of the current config to `glance_haproxy_backup_path`. Re-running the playbook does not replace that rollback copy.

Rendered shape:

```haproxy
frontend glance_admin_local
        bind *:9444
        mode http
        default_backend glance_admin_cluster_local_https

backend glance_admin_cluster_local_https
        mode http
        balance roundrobin
        option httpchk GET /v2/
        http-check expect rstatus 200|401
        server glance01 10.96.13.51:9494 check ssl verify none
        server glance02 10.96.13.208:9494 check ssl verify none
        server glance03 10.96.12.47:9494 check ssl verify none
```

### Managed override files

The playbook creates the override files when they do not exist and manages the required keys with `community.general.ini_file`. Re-running the playbook updates existing keys instead of appending duplicate `[glance]` or `[pf9_glance]` blocks.

```ini
[glance]
endpoint_override = https://localhost:9494

[pf9_glance]
glance_cluster = false
```

Managed files:

- `/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf`
- `/opt/pf9/etc/nova/conf.d/nova_override.conf`

### Pre-check behaviour

| Check | Applies to |
| ---- | -------- |
| `systemctl show pf9-glance-api.service` must report `LoadState=loaded`, and the reported `FragmentPath` or `SourcePath` must exist on disk; otherwise the current host is ended and the play continues on other hosts. | all tasks |
| `systemctl is-active pf9-glance-api.service` must return `active`, or service facts must report `pf9-glance-api.service` / `pf9-glance-api` as `running`; otherwise the current host is ended and the play continues on other hosts. | all tasks |
| `glance_haproxy_cfg_path` must exist before the HAProxy block is appended. | HAProxy only |
| Unmanaged `frontend glance_admin_local` or `backend glance_admin_cluster_local_https` sections must not already exist. | HAProxy only |
| Override file parent directories must already exist because the playbook creates files, not directories. | Cinder and Nova only |

### Sensitive values

The sample inventory and variables intentionally contain placeholders for hostnames, SSH users, source CIDRs, and Glance backend IPs. Do not commit customer-specific values unless this repository is intended to store them.

#### Verification

```bash
# Check playbook syntax
ANSIBLE_LOCAL_TEMP=/private/tmp/ansible-local TMPDIR=/private/tmp \
  ansible-playbook --syntax-check playbooks/configure-glance-isolated-cluster.yml

# Run the playbook
ansible-playbook playbooks/configure-glance-isolated-cluster.yml
```

```bash
# Verify the managed HAProxy block on a target
ansible glance_isolated_cluster_hosts -b -m ansible.builtin.command \
  -a 'grep -A20 "ANSIBLE MANAGED GLANCE LOCAL CLUSTER HTTPS" /etc/haproxy/haproxy.cfg'

# Verify the Cinder override on a target
ansible glance_isolated_cluster_hosts -b -m ansible.builtin.command \
  -a 'cat /opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf'

# Verify the Nova override on a target
ansible glance_isolated_cluster_hosts -b -m ansible.builtin.command \
  -a 'cat /opt/pf9/etc/nova/conf.d/nova_override.conf'
```

## `rollback-glance-isolated-cluster.yml`

Rolls back the managed Glance isolated cluster changes without deleting the host's default HAProxy configuration file.

**Dependencies (local):**

- `ansible-core>=2.14` — required to run the playbook.
- `community.general>=8.0` — required for idempotent INI key removal through `community.general.ini_file`.
- SSH access to each host in the `glance_isolated_cluster_hosts` inventory group.
- A sudo-capable remote user set through `inventory.yaml`.

**Dependencies (remote host):**

- `/etc/haproxy/haproxy.cfg` must exist as a regular file.
- HAProxy must be installed and managed by the `haproxy` service if the managed HAProxy block is removed.
- Platform9 service units `pf9-ostackhost.service` and `pf9-cindervolume-base` must exist if Nova or Cinder override keys are removed.
- Sudo access for editing `/etc/haproxy/haproxy.cfg`, files under `/opt/pf9/etc`, and restarting services.

**What it does:**

1. Checks that `glance_haproxy_cfg_path` exists as a regular file.
2. Removes only the Ansible-managed HAProxy block marked `ANSIBLE MANAGED GLANCE LOCAL CLUSTER HTTPS`.
3. Removes `endpoint_override` from the `[glance]` section in the Cinder override file when that file exists.
4. Removes `glance_cluster` from the `[pf9_glance]` section in the Cinder override file when that file exists.
5. Removes `endpoint_override` from the `[glance]` section in the Nova override file when that file exists.
6. Removes `glance_cluster` from the `[pf9_glance]` section in the Nova override file when that file exists.
7. Restarts `haproxy`, `pf9-cindervolume-base`, and `pf9-ostackhost.service` only when their files change.

### Usage

```bash
# Roll back managed Glance isolated cluster changes
ansible-playbook playbooks/rollback-glance-isolated-cluster.yml
```

### Pre-check behaviour

| Check | Applies to |
| ---- | -------- |
| `glance_haproxy_cfg_path` must exist as a regular file before rollback proceeds. | HAProxy rollback |
| Override files are changed only when they already exist. | Cinder and Nova rollback |

#### Verification

```bash
# Check rollback playbook syntax
ANSIBLE_LOCAL_TEMP=/private/tmp/ansible-local TMPDIR=/private/tmp \
  ansible-playbook --syntax-check playbooks/rollback-glance-isolated-cluster.yml

# Verify the default HAProxy config still exists on a target
ansible glance_isolated_cluster_hosts -b -m ansible.builtin.stat \
  -a 'path=/etc/haproxy/haproxy.cfg'
```
