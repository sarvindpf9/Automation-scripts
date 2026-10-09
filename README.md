# python-edition

Python edition of the local Platform9 host health-check utility.

---

## `hostinfo_check.py`

`hostinfo_check.py` is the Python edition of the local Platform9 host health check. It provides structured terminal output and can write timestamped plain-text, PDF, and JSON reports without modifying host configuration.

<!-- Reports can contain hostnames, IP addresses, iSCSI initiator IQNs, VM names and UUIDs, account records, storage identifiers, and complete configuration-file contents. Review and redact generated files before sharing them. -->

**Dependencies (local):**

- Python 3.9 or newer; the script uses built-in generic type annotations such as `list[str]`
- Python packages from `requirements.txt`: `setuptools`, `python-openstackclient`, `requests`, `reportlab`, and `rich`
- A readable `/etc/os-release`; supported OS IDs are `ubuntu`, `rocky`, `rhel`, and `almalinux`
- `dpkg-query` on Ubuntu or `rpm` on Rocky Linux, RHEL, and AlmaLinux
- Host utilities used by individual checks, including `ip`, `timedatectl`, `systemctl`, `grpck`, `getent`, `iscsiadm`, `multipath`, `ovs-vsctl`, `virsh`, `readlink`, and `stat`
- Root or equivalent read access is recommended because the checks inspect system, Platform9, libvirt, multipath, iSCSI, sudoers, account, `/etc/hosts`, and `/etc/fstab` data

**What it does:**

1. Detects the operating system and selects Debian or RPM package queries.
2. Runs the full host-check suite, selected standalone storage checks, or a single VM check.
3. Displays each result as `OK`, `WARN`, `FAIL`, `INFO`, or `ERROR` in a Rich terminal table.
4. Prints `/etc/hosts` and `/etc/fstab`, reports an unset LVM `filter`/`global_filter` as a warning, and checks the Open vSwitch/OVN packages or command providers required by the host checks.
5. Optionally creates timestamped plain-text, PDF, and JSON reports.

### Ubuntu setup

Use Python 3.9 or newer. Ubuntu releases whose default `python3` is older than 3.9 require an organization-approved Python 3.9+ installation before running the installer.

```bash
# Install the Ubuntu prerequisites
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip tar

# Confirm that the selected interpreter is Python 3.9 or newer
python3 --version
```

### PF9OS Linux setup

It default comes preinstalled with python `3.12.13`. No extra package to be installed 


### Extract the installation bundle

Extract `hostcheck-install.tar.gz` into a dedicated directory and run the installer from that directory. The extracted files must include `pyenv-install.sh`, `requirements.txt`, and `hostinfo_check.py`.

```bash
# Extract the host-check installation bundle
tar -xzf hostcheck-install.tar.gz -C hostcheck-tool-install
cd hostcheck-tool-install

# Confirm that all required files are present
ls -l pyenv-install.sh requirements.txt hostinfo_check.py
```

### Install the Python environment
- Post extracting the tar file, set execution permission to the `pyenv-install.sh`  script and execute it:
```
chmod a+x pyenv-install.sh
./pyenv-install.sh
```

`pyenv-install.sh` creates `/opt/scripts/hostcheck-tool-install/` and `/opt/scripts/hostcheck-tool-install/venv`, upgrades `pip` from `https://pypi.org/simple/`, and installs the packages listed in `requirements.txt`. It requires privileges to create and populate `/opt/scripts/hostcheck-tool-install/` and requires outbound access to PyPI.

After installation:

- The deployed script is `/opt/scripts/hostcheck-tool-install/hostcheck_info.py`.
- The copied dependency file is `/opt/scripts/hostcheck-tool-install/requirements.txt`.
- The virtual environment is `/opt/scripts/hostcheck-tool-install/venv`.
- Re-running the installer invokes `python3 -m venv` on the same environment path and refreshes the Python packages.
- The installer uses `set -euo pipefail` and stops immediately when a required file, copy operation, virtual-environment creation, or package installation fails.

### Usage

- cd into to the `/opt/scripts/hostcheck-tool-install` directory and source the python environment activate file:
```
source venv/bin/activate
```

```bash
# Run the full default host-check suite
./hostinfo_check

# Add the passwordless-sudo check to the full suite
./hostinfo_check check-sudoers

# Run the standalone multipath-orphan check
./hostinfo_check check-mpath-orphan

# Inspect multipath devices used by running VMs
./hostinfo_check list-vm-mpath

# Check the default Glance image-library mount
./hostinfo_check check-glance-mount

# Check a specified Glance image-library directory
./hostinfo_check \
  check-glance-mount \
  <GLANCE_MOUNT_DIRECTORY>

# Inspect one VM by UUID
./hostinfo_check --uuid <VM_UUID>

# Create text, PDF, and JSON reports in one run
./hostinfo_check \
  --output <TEXT_REPORT_PATH> \
  --pdf <PDF_REPORT_PATH> \
  --json <JSON_REPORT_PATH>
```
The same commands can be executed without sourcing the venv by following way of calling the script:
```
sudo /opt/scripts/venv/bin/python /opt/scripts/./hostinfo_check 
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `check-sudoers` | No | Adds the passwordless-sudo scan to the full default suite. |
| `check-mpath-orphan` | No | Runs the standalone multipath-orphan check. |
| `list-vm-mpath` | No | Runs the standalone per-VM multipath check. |
| `check-glance-mount` | No | Runs the standalone Glance mount check. It accepts an optional positional directory or `--glance-mount-dir`. |
| `--glance-mount-dir <DIRECTORY>` | No | Sets the Glance mount directory. The default is `/var/opt/imagelibrary`. |
| `--uuid <VM_UUID>` | No | Runs the single-VM libvirt and multipath check when no standalone storage selector is present. |
| `--log` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory. Mutually exclusive with `--output`. |
| `--output <FILE>` | No | Writes a timestamped plain-text report derived from `FILE`. Mutually exclusive with `--log`. |
| `--pdf <FILE>` | No | Writes a timestamped, color-coded PDF report. Requires `reportlab`. |
| `--json <FILE>` | No | Writes a timestamped, machine-readable JSON report. |

Standalone selectors take precedence over `--uuid` and the full suite. Multiple standalone selectors can be supplied together. `--pdf` and `--json` can be combined with terminal-only output, `--log`, or `--output`.

### Output and exit behaviour

- Requested report filenames receive a `-<YYYYMMDD_HHMMSS>` suffix before their extension.
- A successful run returns `0` only when no check reports `FAIL` or `ERROR`.
- A completed report containing at least one `FAIL` or `ERROR` returns `1`.
- Initialization, report-writing, and dependency errors return `2`.
- An unset LVM `filter` and `global_filter` is reported as `WARN`; a missing or unreadable `/etc/lvm/lvm.conf` remains `FAIL`.
- `/etc/fstab` is included in the default report. An unreadable file is reported as `FAIL`.

### Sensitive output

Terminal and generated reports can expose infrastructure and account details. Store report files with access controls appropriate for operational data, and redact them before external sharing.

### Example outputs:
- help section:
```
./hostinfo_check -h
usage: hostinfo_check.py [-h] [--uuid UUID] [--glance-mount-dir GLANCE_MOUNT_DIR] [--log | --output OUTPUT] [--pdf] [--json] [CHECK ...]

Run Platform9 host readiness and storage checks.

positional arguments:
  CHECK                 optional standalone check: check-sudoers, check-mpath-orphan, list-vm-mpath, or check-glance-mount (default: None)

options:
  -h, --help            show this help message and exit
  --uuid UUID           check one virsh VM and its multipath disks (default: None)
  --glance-mount-dir GLANCE_MOUNT_DIR
                        directory used by check-glance-mount (default: /var/opt/imagelibrary)
  --log                 write a timestamped plain-text copy of the report (default: False)
  --output OUTPUT       write a plain-text report (default: None)
  --pdf                 write a timestamped color-coded PDF report (default: False)
  --json                write a timestamped machine-parseable JSON report (default: False)
```

- 