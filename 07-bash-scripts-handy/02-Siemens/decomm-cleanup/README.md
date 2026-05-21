# decomm-cleanup

Remotely decommissions PCD nodes over SSH by running targeted cleanup steps — package inspection, fstab sanitisation, unmounting, artifact removal, and node deauthorisation — each independently selectable via flags.

---

## Decommission Workflow

The steps below apply to `decomm-cleanup-v3.sh`. Run them in the order shown — deauthorisation must be allowed to propagate before decommission is triggered.

### 1. Prepare the host list

Create a file named `host-list` with one hostname per line:

```text
<HOSTNAME_1>
<HOSTNAME_2>
<HOSTNAME_3>
```

### 2. Fix fstab entries

Comment out PF9-related fstab mount entries on all hosts:

```bash
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --fix-fstab
```

### 3. Trigger deauthorisation

```bash
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --deauth
```

Wait for deauthorisation to propagate through the PCD control plane before continuing.

### 4. Unmount data paths

```bash
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --unmount
```

### 5. Decommission

```bash
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --decommission
```

### 6. Verify — stale directories and PF9 services

Once decommission exits, run both checks to confirm the hosts are clean:

```bash
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --check-dirs
./decomm-cleanup-v3.sh -f host-list -u <SSH_USER> -p '<SSH_PASSWORD>' --check-pf9
```

Expected: `--check-dirs` reports all paths `[ABSENT]`; `--check-pf9` returns no installed PF9 packages.

---

## `decomm-cleanup.sh`

Reads a list of hosts from a file, connects to each one using username/password SSH via `sshpass`, escalates to root with `sudo`, and executes the requested cleanup steps in sequence. Steps are function-scoped and flag-driven; any combination can be run in a single invocation.

**Dependencies (local):**

- `sshpass` — supplies the SSH password non-interactively (`apt install sshpass` / `yum install sshpass`)
- `base64`, `tr` — used internally to encode remote scripts so the sudo password and script body do not share stdin
- A hosts file — plain text, one hostname or IP per line; lines starting with `#` and blank lines are skipped

**Dependencies (remote host):**

- `bash` — remote scripts are executed via `sudo bash`
- `sudo` — must be available and configured to allow the SSH user to escalate; the SSH password is reused for `sudo -S`
- `dpkg` — required for `--check-pf9`
- `mountpoint`, `umount` — required for `--unmount`
- `pcdctl` — required for `--decommission` and `--deauth`; must be on root's `PATH`

**What it does:**

1. Validates required arguments (`-f`, `-u`, `-p`) and that at least one action flag is set.
2. Checks that `sshpass` is installed locally; exits with a clear message if not.
3. For each host in the hosts file, opens an SSH session as the specified user and escalates to root via `sudo -S`.
4. Runs each enabled step in order: `--check-pf9` → `--fix-fstab` → `--unmount` → `--check-dirs` → `--clean-dirs` → `--decommission` → `--deauth`.
5. On a per-host step failure, prints a `[WARN]` line and continues to the next step rather than aborting.

### Usage

```bash
# Run all non-destructive steps on every host in the list
./decomm-cleanup.sh \
  -f hosts.txt \
  -u <SSH_USER> \
  -p <SSH_PASSWORD> \
  --all

# Run a single targeted step
./decomm-cleanup.sh \
  -f hosts.txt \
  -u <SSH_USER> \
  -p <SSH_PASSWORD> \
  --check-pf9

# Audit artifact paths then delete them (--clean-dirs must be passed explicitly)
./decomm-cleanup.sh \
  -f hosts.txt \
  -u <SSH_USER> \
  -p <SSH_PASSWORD> \
  --check-dirs --clean-dirs
```

> **Note — sensitive arguments:** `-u` and `-p` are supplied on the command line.
> Avoid embedding credentials in shell history; prefer wrapping the invocation in a short script that sources them from a secrets store or environment variable.

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `-f <file>` | Yes | Path to hosts file; one hostname or IP per line. |
| `-u <user>` | Yes | SSH username used to connect and for `sudo -S`. |
| `-p <password>` | Yes | SSH password; reused as the sudo password. |
| `--check-pf9` | No | Runs `dpkg -l \| grep -i pf9` on each host and prints installed PF9 packages. |
| `--fix-fstab` | No | Comments out any active `/etc/fstab` entries for `opt/data/instances` and `var/lib/glance/images`. Leaves all other entries untouched. Creates a `.bak` of the original. |
| `--unmount` | No | Checks if `/opt/data/instances` and `/var/lib/glance/images` are currently mounted; unmounts them with `umount -vvv` if so. |
| `--check-dirs` | No | Reports presence or absence of known PF9 artifact paths. Found paths are highlighted in yellow. Included in `--all`. |
| `--clean-dirs` | No | Deletes the PF9 artifact paths listed below. **DESTRUCTIVE — not included in `--all`; must be passed explicitly.** |
| `--decommission` | No | Runs two remote pre-checks (PF9 package count + artifact path count) before executing `pcdctl decommission-node --verbose --no-prompt`. If both counts are zero the host is reported as already decommissioned and the `pcdctl` call is skipped. Included in `--all`. |
| `--deauth` | No | Runs `pcdctl deauthorize-node --verbose --no-prompt` as root. Included in `--all`. |
| `--all` | No | Runs `--check-pf9`, `--fix-fstab`, `--unmount`, `--check-dirs`, `--decommission`, and `--deauth` in that order. Does **not** include `--clean-dirs`. |
| `-h` / `--help` | No | Prints usage and exits. |

### PF9 artifact paths (`--check-dirs` / `--clean-dirs`)

Both flags operate on the same fixed list of paths:

| Path | Type |
| ---- | ---- |
| `/etc/pf9` | directory |
| `/var/log/pf9` | directory |
| `/var/spool/mail/pf9` | file |
| `/root/pf9` | directory |
| `/var/opt/imagelibrary/data/glance` | directory |
| `/opt/data/instances` | directory |
| `/opt/pf9/data/state/compute_id` | file |
| `/var/opt/pf9/neutron/metadata_proxy` | file / socket |
| `/opt/pf9/data/locks` | directory |
| `/opt/pf9/python` | directory |
| `/etc/pf9_environment` | file |

`--check-dirs` prints `[FOUND]` (yellow) or `[ABSENT]` for each path and a summary count.
`--clean-dirs` runs `rm -rf` on each present path and prints `[DELETED]` (red) or `[SKIP]`.

### `--fix-fstab` behaviour

Only active (non-commented) lines containing the target mount paths are modified. The sed substitution prepends `#` to the matching line; all other fstab entries are left exactly as-is. A `.bak` copy of the original is written by `sed -i.bak` before any change is made. The updated fstab is printed (indented) only when at least one line was changed.

### `--unmount` behaviour

Uses `mountpoint -q` to confirm each path is actually mounted before calling `umount`. If a path is absent or not a mountpoint, it is skipped with `[SKIP]` — no error is raised.

### `--decommission` pre-check behaviour

Before invoking `pcdctl decommission-node`, the function runs two lightweight remote checks in parallel:

| Check | Method |
| ----- | ------ |
| PF9 package count | `dpkg -l \| grep -ic pf9` |
| PF9 artifact path count | presence test across the 11 paths in the `--check-dirs` list |

If **both** counts are zero, the host is considered already clean and the `pcdctl` call is skipped with:

```
  [SKIP] host already decommissioned — no PF9 packages and no artifact paths found
```

If either count is non-zero, a summary line is printed and `pcdctl decommission-node --verbose --no-prompt` is executed:

```
  Pre-check: 3 PF9 package(s), 5 artifact path(s) present — proceeding
```

This pre-check runs independently of whether `--check-pf9` or `--check-dirs` were also passed on the same invocation.

### SSH connection and sudo escalation

The script encodes each remote script as base64 and passes it as a `bash -c` argument. This keeps the sudo password and the script body on separate stdin/argument channels, avoiding the failure mode where the password leaks into bash as a command.

SSH options applied to every connection:

| Option | Value |
| ------ | ----- |
| `StrictHostKeyChecking` | `no` |
| `ConnectTimeout` | `10` seconds |
| `PasswordAuthentication` | `yes` |

### Example output

```
============================================================
 HOST: 10.0.0.21
============================================================
==> [10.0.0.21] PF9 packages
ii  pf9-hostagent  4.7.0  amd64  Platform9 host agent

==> [10.0.0.21] /etc/fstab
  [COMMENTED] /dev/sdb  /opt/data/instances  ext4  defaults  0  0
  [SKIP]      no active entry matching: var/lib/glance/images

  /etc/fstab (current state):
  ------------------------------------------------------------
  UUID=abc123  /  ext4  defaults  0  1
  #/dev/sdb  /opt/data/instances  ext4  defaults  0  0
  ------------------------------------------------------------

==> [10.0.0.21] Unmounting data paths
  [UNMOUNT] /opt/data/instances is mounted — running umount -vvv
  [SKIP]    /var/lib/glance/images is not mounted

==> [10.0.0.21] PF9 artifact paths
  [FOUND]   /etc/pf9                                           (dir)
  [FOUND]   /var/log/pf9                                       (dir)
  [ABSENT]  /var/spool/mail/pf9
  ...
  4 of 11 paths present

==> [10.0.0.21] pcdctl decommission-node
  Pre-check: 3 PF9 package(s), 4 artifact path(s) present — proceeding
  ... pcdctl verbose output ...

# Example when host is already clean:
==> [10.0.0.22] pcdctl decommission-node
  [SKIP] host already decommissioned — no PF9 packages and no artifact paths found

==> [10.0.0.21] pcdctl deauthorize-node
  ... pcdctl verbose output ...

Done.
```
