# python-edition

Python edition of the local Platform9 host health-check utility.

---

## `hostinfo_check.py`

`hostinfo_check.py` is the Python edition of the local Platform9 host health check. It provides structured terminal output and can write timestamped plain-text, PDF, and JSON reports without modifying host configuration.

<!-- Reports can contain hostnames, IP addresses, iSCSI initiator IQNs, VM names and UUIDs, account records, storage identifiers, and complete configuration-file contents. Review and redact generated files before sharing them. -->

**Dependencies (local):**

- Script should be executed as `root` user to be more effective in collecting the required data
- Python 3.9 or newer; the script uses built-in generic type annotations such as `list[str]`
- Python packages from `requirements.txt`: `setuptools`, `python-openstackclient`, `requests`, `reportlab`, and `rich`
- A readable `/etc/os-release`; supported OS IDs are `ubuntu`, `rocky`, `rhel`, and `almalinux`
- `dpkg-query` on Ubuntu or `rpm` on Rocky Linux, RHEL, and AlmaLinux
- Host utilities used by individual checks, including `ip`, `timedatectl`, `systemctl`, `grpck`, `getent`, `iscsiadm`, `nvme`, `multipath`, `ovs-vsctl`, `virsh`, `readlink`, and `stat`
- Root or equivalent read access is recommended because the checks inspect system, Platform9, libvirt, multipath, iSCSI, sudoers, account, `/etc/hosts`, and `/etc/fstab` data

**What it does:**

1. Detects the operating system and selects Debian or RPM package queries.
2. Runs the full host-check suite, every non-parameterized check, the core storage-only report, selected standalone storage checks, or a single VM check.
3. Displays each result as `OK`, `WARN`, `FAIL`, `INFO`, or `ERROR` in a Rich terminal table.
4. Prints `/etc/hosts` and `/etc/fstab`, reports an unset LVM `filter`/`global_filter` as a warning, and checks the Open vSwitch/OVN packages or command providers required by the host checks.
5. Detects dedicated CPU or hugepage parameters in `/proc/cmdline` and conditionally runs the kernel command-line, CPU-isolation, hugepage-allocation, and IRQ-placement checks. When no matching parameter exists, each section reports that no dedicated CPU or memory configuration was found.
6. Runs the NIC-passthrough checks when `vfio_pci` is loaded; otherwise, the section reports that no NIC passthrough settings are configured.
7. Optionally creates timestamped plain-text, PDF, and JSON reports containing the same sections displayed in the terminal.
8. Validates the NVMe CLI, required runtime and persistent kernel modules, native multipath, host identity files, and the NVMe subsystems attached to running VMs.

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

On Ubuntu 24.04 LTS, the installer runs `apt-get install python3.12-venv -yy` before creating the virtual environment. Other operating systems continue directly to the existing installation steps.

After installation:

- The deployed script is `/opt/scripts/hostcheck-tool-install/hostinfo_check`.
- The copied dependency file is `/opt/scripts/hostcheck-tool-install/requirements.txt`.
- The virtual environment is `/opt/scripts/hostcheck-tool-install/venv`.
- Re-running the installer invokes `python3 -m venv` on the same environment path and refreshes the Python packages. When the source and destination `requirements.txt` are the same file, the copy is skipped so the installation can complete and print the final usage instructions.
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

# Inspect NVMe devices attached to running VMs
./hostinfo_check list-nvme-vm

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

# Run only the CPU, hugepage, IRQ, KVM, NIC-passthrough, and Nova checks
./hostinfo_check --resource-isolate-settings

# Run all optional checks, including the complete resource-isolation report
./hostinfo_check --all-optional

# Run every non-parameterized check, including passwordless sudo
./hostinfo_check --run-all

# Run only the core NVMe, iSCSI, FC, multipath, and LVM storage checks
./hostinfo_check --storage-check

# Write the storage-only report as plain text, PDF, and JSON
./hostinfo_check \
  --storage-check \
  --log \
  --pdf \
  --json

# Create text, PDF, and JSON reports in one run
./hostinfo_check \
  --output <TEXT_REPORT_PATH> \
  --pdf \
  --json
```
The same commands can be executed without sourcing the venv by following way of calling the script:
```
sudo /opt/scripts/venv/bin/python /opt/scripts/./hostinfo_check 
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `-h`, `--help` | No | Displays the command-line help and exits. |
| `check-sudoers` | No | Adds the passwordless-sudo scan to the full default suite. |
| `check-mpath-orphan` | No | Runs the standalone multipath-orphan check. |
| `list-nvme-vm` | No | Maps disks attached to running VMs to NVMe subsystems and verifies that each subsystem host NQN matches `/etc/nvme/hostnqn`. Non-NVMe disks are identified without failing the check. |
| `list-vm-mpath` | No | Inspects every disk attached to each running VM and reports its dm-multipath mapping and path state, or identifies it as a non-multipath disk. |
| `check-glance-mount` | No | Runs the standalone Glance mount check. It accepts an optional positional directory or `--glance-mount-dir`. |
| `--glance-mount-dir <DIRECTORY>` | No | Sets the Glance mount directory. The default is `/var/opt/imagelibrary`. |
| `--uuid <VM_UUID>` | No | Runs the single-VM libvirt and multipath check when no standalone storage selector is present. |
| `--virsh` | No | Hidden compatibility flag accepted by the parser. It does not alter check selection or report content. |
| `--resource-isolate-settings` | No | Runs only the CPU, hugepage, IRQ, KVM, NIC-passthrough, and Nova resource-isolation report. |
| `--all-optional` | No | Runs all optional storage checks, including the per-VM NVMe attachment check, and the complete resource-isolation report, excluding the passwordless-sudo listing. |
| `--run-all` | No | Runs every non-parameterized check: the default suite, passwordless-sudo listing, standalone storage checks, and complete resource-isolation report. It overrides `--storage-check` and `--resource-isolate-settings`; if `--uuid` is also supplied, that VM check is included. |
| `--storage-check` | No | Runs only `NVME CONFIGURATION`, `ISCSI INITIATOR`, `FC PORTS`, `ISCSID CONF`, `MULTIPATH BLACKLIST`, and `LVM FILTERS`. |
| `--log` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory. Mutually exclusive with `--output`. |
| `--output <FILE>` | No | Writes a timestamped plain-text report derived from `FILE`. Mutually exclusive with `--log`. |
| `--pdf` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.pdf`. Requires `reportlab`. |
| `--json` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.json`. |

Standalone selectors take precedence over `--uuid` and the full suite. Multiple standalone selectors can be supplied together. `--resource-isolate-settings` runs only its specific report. `--all-optional` includes the standalone storage checks and the complete resource-isolation report in the full suite. Unless `--run-all` is present, `--storage-check` takes precedence when combined with other selection flags, including `--all-optional`, and runs only its six core storage sections. `--run-all` overrides the storage-only and resource-isolation-only modes. `--pdf` and `--json` can be combined with terminal-only output, `--log`, or `--output`; every requested format receives the same collected check sections.

### Output and exit behaviour

- Requested report filenames receive a `-<YYYYMMDD_HHMMSS>` suffix before their extension.
- A successful run returns `0` only when no check reports `FAIL` or `ERROR`.
- A completed report containing at least one `FAIL` or `ERROR` returns `1`.
- Initialization, report-writing, and dependency errors return `2`.
- An unset LVM `filter` and `global_filter` is reported as `WARN`; a missing or unreadable `/etc/lvm/lvm.conf` remains `FAIL`.
- Missing PF9 rsyslog configuration or rules are reported as `WARN`.
- `/etc/fstab` is included in the default report. An unreadable file is reported as `FAIL`.
- The default suite conditionally includes resource-isolation sections based on `/proc/cmdline` and the loaded `vfio_pci` module. Skipped sections remain visible with an `INFO` result explaining why they were skipped.
- `--all-optional` includes the complete resource-isolation report and the standalone NVMe VM-attachment report. Terminal, plain-text, PDF, and JSON outputs receive the same report collection, including skip messages and the process-column header in `Processes on isolated CPUs`.
- The FC check inventories remote ports whose role contains `Target`, relates each `rport-*` to its local `hostN`, and reports each target WWPN. An online local FC port with no visible FCP targets is reported as `WARN` with zoning, zoneset, target-port, and fabric guidance.
- `NVME CONFIGURATION` checks `nvme-cli`, the `nvme_tcp`, `nvme_fabrics`, `nvme_keyring`, `nvme_core`, and `nvme_auth` runtime modules, persistent `nvme_tcp` and `nvme_fabrics` configuration, native NVMe multipath, `/etc/nvme/hostnqn`, and `/etc/nvme/hostid`.
- `--storage-check` sends the same six storage sections to terminal, plain-text, PDF, and JSON output. A failing storage result still produces requested report files and returns `1`.

### Sensitive output

Terminal and generated reports can expose infrastructure and account details. Store report files with access controls appropriate for operational data, and redact them before external sharing.

### Example outputs:
- help section output:
```
./hostinfo_check -h
usage: hostinfo_check.py [-h] [--uuid UUID] [--all-optional]
                         [--resource-isolate-settings] [--storage-check]
                         [--glance-mount-dir GLANCE_MOUNT_DIR]
                         [--log | --output OUTPUT] [--pdf] [--json]
                         [CHECK ...]

Run Platform9 host readiness and storage checks.

positional arguments:
  CHECK                 optional standalone check: check-sudoers, check-mpath-orphan, list-vm-mpath, or check-glance-mount (default: None)

options:
  -h, --help            show this help message and exit
  --uuid UUID           check one virsh VM and its multipath disks (default: None)
  --all-optional        run all optional checks, including resource-isolation
                        settings, except the passwordless sudo user listing;
                        results are included in requested log, JSON, and PDF
                        reports (default: False)
  --resource-isolate-settings
                        run only CPU, hugepage, IRQ, KVM, and PCI passthrough
                        checks (default: False)
  --storage-check       run only iSCSI initiator, FC ports, iscsid
                        configuration, multipath blacklist, and LVM filter
                        checks (default: False)
  --glance-mount-dir GLANCE_MOUNT_DIR
                        directory used by check-glance-mount (default: /var/opt/imagelibrary)
  --log                 write a timestamped plain-text copy of the report (default: False)
  --output OUTPUT       write a plain-text report (default: None)
  --pdf                 write a timestamped color-coded PDF report (default: False)
  --json                write a timestamped machine-parseable JSON report (default: False)
```

- Print with all options set:
```
./hostinfo_check.py --all-optional
hostInfo-check                                                   
╭─────────────────────────────────────┬─────────────────────────╮
│ Host Name                           │ Report Time             │
├─────────────────────────────────────┼─────────────────────────┤
│ test-pf9-testbed-only-5305247-260-1 │ 2026-11-02 10:40:47 UTC │
╰─────────────────────────────────────┴─────────────────────────╯

ENVIRONMENT                                         
╭──────────────────┬──────────┬────────────────────╮
│ Check            │  Status  │ Output             │
├──────────────────┼──────────┼────────────────────┤
│ Operating system │    OK    │ Ubuntu 24.04.4 LTS │
╰──────────────────┴──────────┴────────────────────╯

MULTIPATH ORPHANS                                            
╭───────────────────┬──────────┬────────────────────────────╮
│ Check             │  Status  │ Output                     │
├───────────────────┼──────────┼────────────────────────────┤
│ Multipath orphans │   WARN   │ no multipath devices found │
╰───────────────────┴──────────┴────────────────────────────╯

VM NVME ATTACHMENTS                                                                                                                                                                                                                        
╭────────────────────────────────────────────────────────────────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ VM UUID->root Disk                                                                 │  Status  │ Output                                                                                                                                  │
├────────────────────────────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 41f4764c-7222-429e-89cc-0f6dbc8f10dc (41f4764c-7222-429e-89cc-0f6dbc8f10dc) -> vda │    OK    │ device: /dev/nvme0n1; hostnqn matches /etc/nvme/hostnqn                                                                                 │
│                                                                                    │          │ nvme-subsys0 - NQN=nqn.1992-08.com.netapp:sn.81ff852fd14e11f18bf100a0b8ccb969:subsystem.openstack-a4e693dc-9aa2-4f78-a45e-8489742db373  │
│                                                                                    │          │                hostnqn=nqn.2014-08.org.nvmexpress:uuid:cb4d001f-95e3-4682-809d-5754b220ae2b                                             │
│                                                                                    │          │                iopolicy=round-robin                                                                                                     │
│                                                                                    │          │ \                                                                                                                                       │
│                                                                                    │          │  +- nvme0 tcp traddr=10.9.1.216,trsvcid=4420,src_addr=10.10.12.245 live optimized                                                       │
│                                                                                    │          │  +- nvme1 tcp traddr=10.9.1.219,trsvcid=4420,src_addr=10.10.12.245 live optimized                                                       │
├────────────────────────────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 04eb6ee9-04a3-4ee3-b14f-02f804ab306f (04eb6ee9-04a3-4ee3-b14f-02f804ab306f) -> vda │ non-nVMe │ source: volumes/volume-738ca215-7272-4907-b21a-3fada44456e4                                                                             │
│                                                                                    │          │ resolved: volumes/volume-738ca215-7272-4907-b21a-3fada44456e4                                                                           │
├────────────────────────────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8 (c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8) -> vda │ non-nVMe │ source:                                                                                                                                 │
│                                                                                    │          │ /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-6f4ed8f3-3f69-4d77-bb4d-db80614f5676.efce1fd6-1a04-46b3-832f-9d53560ae3 │
│                                                                                    │          │ 5e                                                                                                                                      │
│                                                                                    │          │ resolved:                                                                                                                               │
│                                                                                    │          │ /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-6f4ed8f3-3f69-4d77-bb4d-db80614f5676.efce1fd6-1a04-46b3-832f-9d53560ae3 │
│                                                                                    │          │ 5e                                                                                                                                      │
├────────────────────────────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8 (c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8) -> vdb │ non-nVMe │ source: /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-53c13f47-1adb-4fd9-ba93-87cd82ddc2db                            │
│                                                                                    │          │ resolved: /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-53c13f47-1adb-4fd9-ba93-87cd82ddc2db                          │
╰────────────────────────────────────────────────────────────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

VM DISK MULTIPATH                                                                                                                                                                                                                          
╭───────────────────────────────────────────┬──────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check                                     │        Status        │ Output                                                                                                                                                               │
├───────────────────────────────────────────┼──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 41f4764c-7222-429e-89cc-0f6dbc8f10dc: vda │  non-multipath disk  │ UUID: 41f4764c-7222-429e-89cc-0f6dbc8f10dc; source: /dev/nvme0n1; resolved: /dev/nvme0n1                                                                             │
│                                           │                      │ VM appears to disk which are not managed by dm-multipath services                                                                                                    │
├───────────────────────────────────────────┼──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 04eb6ee9-04a3-4ee3-b14f-02f804ab306f: vda │  non-multipath disk  │ UUID: 04eb6ee9-04a3-4ee3-b14f-02f804ab306f; source: volumes/volume-738ca215-7272-4907-b21a-3fada44456e4; resolved:                                                   │
│                                           │                      │ volumes/volume-738ca215-7272-4907-b21a-3fada44456e4                                                                                                                  │
│                                           │                      │ VM appears to disk which are not managed by dm-multipath services                                                                                                    │
├───────────────────────────────────────────┼──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8: vda │  non-multipath disk  │ UUID: c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8; source:                                                                                                                  │
│                                           │                      │ /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-6f4ed8f3-3f69-4d77-bb4d-db80614f5676.efce1fd6-1a04-46b3-832f-9d53560ae35e; resolved:                 │
│                                           │                      │ /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-6f4ed8f3-3f69-4d77-bb4d-db80614f5676.efce1fd6-1a04-46b3-832f-9d53560ae35e                            │
│                                           │                      │ VM appears to disk which are not managed by dm-multipath services                                                                                                    │
├───────────────────────────────────────────┼──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8: vdb │  non-multipath disk  │ UUID: c13bffde-4cc3-4cc6-bd2d-57b1ea9762c8; source: /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-53c13f47-1adb-4fd9-ba93-87cd82ddc2db; resolved:  │
│                                           │                      │ /opt/pf9/data/state/mnt/c5a57b9b94038b51a696b34cf6bb9a88/volume-53c13f47-1adb-4fd9-ba93-87cd82ddc2db                                                                 │
│                                           │                      │ VM appears to disk which are not managed by dm-multipath services                                                                                                    │
╰───────────────────────────────────────────┴──────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

GLANCE IMAGE MOUNT                                                    
╭──────────────────────────┬──────────┬──────────────────────────────╮
│ Check                    │  Status  │ Output                       │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ Glance mount mapping     │    OK    │ /var/opt/imagelibrary/data   │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ Glance mount permissions │   FAIL   │ ╭────────┬──────────╮        │
│                          │          │ │ Actual │ Expected │        │
│                          │          │ ├────────┼──────────┤        │
│                          │          │ │ 755    │ 744      │        │
│                          │          │ ╰────────┴──────────╯        │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ Glance mount ownership   │   FAIL   │ ╭───────────┬──────────────╮ │
│                          │          │ │ Actual    │ Expected     │ │
│                          │          │ ├───────────┼──────────────┤ │
│                          │          │ │ root:root │ pf9:pf9group │ │
│                          │          │ ╰───────────┴──────────────╯ │
╰──────────────────────────┴──────────┴──────────────────────────────╯

PASSWORDLESS SUDO                                                             
╭───────────────────┬──────────┬─────────────────────────────────────────────╮
│ Check             │  Status  │ Output                                      │
├───────────────────┼──────────┼─────────────────────────────────────────────┤
│ Passwordless sudo │    OK    │ ubuntu (/etc/sudoers.d/90-cloud-init-users) │
╰───────────────────┴──────────┴─────────────────────────────────────────────╯

CHECK BOND MODE                                          
╭─────────────────┬──────────┬──────────────────────────╮
│ Check           │  Status  │ Output                   │
├─────────────────┼──────────┼──────────────────────────┤
│ Bond interfaces │   WARN   │ no bond interfaces found │
╰─────────────────┴──────────┴──────────────────────────╯

NTP                                        
╭─────────────────────┬──────────┬────────╮
│ Check               │  Status  │ Output │
├─────────────────────┼──────────┼────────┤
│ NTP synchronization │    OK    │ yes    │
╰─────────────────────┴──────────┴────────╯

SYSCTL SETTINGS                                                                      
╭──────────────────────────────────┬──────────┬─────────────────────────────────────╮
│ Check                            │  Status  │ Output                              │
├──────────────────────────────────┼──────────┼─────────────────────────────────────┤
│ Runtime net.ipv4.tcp_retries2    │    OK    │ ╭────────┬──────────╮               │
│                                  │          │ │ Actual │ Expected │               │
│                                  │          │ ├────────┼──────────┤               │
│                                  │          │ │ 7      │ 7        │               │
│                                  │          │ ╰────────┴──────────╯               │
├──────────────────────────────────┼──────────┼─────────────────────────────────────┤
│ Persistent net.ipv4.tcp_retries2 │    OK    │ /etc/sysctl.d/90-pf9-hostagent.conf │
├──────────────────────────────────┼──────────┼─────────────────────────────────────┤
│ Runtime vm.swappiness            │   WARN   │ ╭────────┬──────────╮               │
│                                  │          │ │ Actual │ Expected │               │
│                                  │          │ ├────────┼──────────┤               │
│                                  │          │ │ 60     │ 10       │               │
│                                  │          │ ╰────────┴──────────╯               │
├──────────────────────────────────┼──────────┼─────────────────────────────────────┤
│ Persistent vm.swappiness         │   FAIL   │ not found under /etc/sysctl.d       │
╰──────────────────────────────────┴──────────┴─────────────────────────────────────╯

PACKAGES                                                          
╭─────────────────────────┬──────────┬───────────────────────────╮
│ Check                   │  Status  │ Output                    │
├─────────────────────────┼──────────┼───────────────────────────┤
│ SCSI device listing     │    OK    │ package: lsscsi           │
├─────────────────────────┼──────────┼───────────────────────────┤
│ SCSI generic utilities  │    OK    │ package: sg3-utils        │
├─────────────────────────┼──────────┼───────────────────────────┤
│ Device mapper multipath │    OK    │ package: multipath-tools  │
├─────────────────────────┼──────────┼───────────────────────────┤
│ SCSI tools              │   FAIL   │ none installed: scsitools │
├─────────────────────────┼──────────┼───────────────────────────┤
│ iSCSI initiator         │    OK    │ package: open-iscsi       │
├─────────────────────────┼──────────┼───────────────────────────┤
│ NFS client              │    OK    │ package: nfs-common       │
╰─────────────────────────┴──────────┴───────────────────────────╯

SERVICES                           
╭────────────┬──────────┬─────────╮
│ Check      │  Status  │ Output  │
├────────────┼──────────┼─────────┤
│ iscsid     │    OK    │ running │
├────────────┼──────────┼─────────┤
│ multipathd │    OK    │ running │
╰────────────┴──────────┴─────────╯

NVME CONFIGURATION                                                                                                  
╭────────────────────────────────┬──────────┬──────────────────────────────────────────────────────────────────────╮
│ Check                          │  Status  │ Output                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ nvme-cli                       │    OK    │ command: /usr/sbin/nvme                                              │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Runtime module nvme_tcp        │    OK    │ loaded                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Runtime module nvme_fabrics    │    OK    │ loaded                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Runtime module nvme_keyring    │    OK    │ loaded                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Runtime module nvme_core       │    OK    │ loaded                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Runtime module nvme_auth       │    OK    │ loaded                                                               │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Persistent module nvme_tcp     │    OK    │ /etc/modules-load.d/nvme-tcp.conf                                    │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ Persistent module nvme_fabrics │   WARN   │ not found in /etc/modprobe.d or /etc/modules-load.d                  │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ NVMe native multipath          │    OK    │ Y                                                                    │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ NVMe host NQN                  │    OK    │ nqn.2014-08.org.nvmexpress:uuid:cb4d001f-95e3-4682-809d-5754b220ae2b │
├────────────────────────────────┼──────────┼──────────────────────────────────────────────────────────────────────┤
│ NVMe host ID                   │    OK    │ 56741e93-31b1-4bca-9033-9369cac22d0e                                 │
╰────────────────────────────────┴──────────┴──────────────────────────────────────────────────────────────────────╯

ISCSI INITIATOR                                                            
╭──────────────────────┬──────────┬───────────────────────────────────────╮
│ Check                │  Status  │ Output                                │
├──────────────────────┼──────────┼───────────────────────────────────────┤
│ iSCSI initiator name │    OK    │ iqn.2004-10.com.ubuntu:01:b8747332a2c │
├──────────────────────┼──────────┼───────────────────────────────────────┤
│ iscsid               │    OK    │ running                               │
├──────────────────────┼──────────┼───────────────────────────────────────┤
│ iSCSI sessions       │   WARN   │ no active sessions                    │
╰──────────────────────┴──────────┴───────────────────────────────────────╯

FC PORTS                                                                                  
╭──────────┬──────────┬──────────────────────────────────────────────────────────────────╮
│ Check    │  Status  │ Output                                                           │
├──────────┼──────────┼──────────────────────────────────────────────────────────────────┤
│ FC ports │   WARN   │ no FC ports found on this node (/sys/class/fc_host/host* absent) │
╰──────────┴──────────┴──────────────────────────────────────────────────────────────────╯

ISCSID CONF                                                                   
╭─────────────────────────────────────────┬──────────┬───────────────────────╮
│ Check                                   │  Status  │ Output                │
├─────────────────────────────────────────┼──────────┼───────────────────────┤
│ node.session.timeo.replacement_timeout  │   WARN   │ ╭────────┬──────────╮ │
│                                         │          │ │ Actual │ Expected │ │
│                                         │          │ ├────────┼──────────┤ │
│                                         │          │ │ 120    │ 15       │ │
│                                         │          │ ╰────────┴──────────╯ │
├─────────────────────────────────────────┼──────────┼───────────────────────┤
│ node.conn[0].timeo.login_timeout        │   WARN   │ ╭────────┬──────────╮ │
│                                         │          │ │ Actual │ Expected │ │
│                                         │          │ ├────────┼──────────┤ │
│                                         │          │ │ 15     │ 5        │ │
│                                         │          │ ╰────────┴──────────╯ │
├─────────────────────────────────────────┼──────────┼───────────────────────┤
│ node.conn[0].timeo.logout_timeout       │   WARN   │ ╭────────┬──────────╮ │
│                                         │          │ │ Actual │ Expected │ │
│                                         │          │ ├────────┼──────────┤ │
│                                         │          │ │ 15     │ 5        │ │
│                                         │          │ ╰────────┴──────────╯ │
├─────────────────────────────────────────┼──────────┼───────────────────────┤
│ node.session.err_timeo.abort_timeout    │   WARN   │ ╭────────┬──────────╮ │
│                                         │          │ │ Actual │ Expected │ │
│                                         │          │ ├────────┼──────────┤ │
│                                         │          │ │ 15     │ 10       │ │
│                                         │          │ ╰────────┴──────────╯ │
├─────────────────────────────────────────┼──────────┼───────────────────────┤
│ node.session.err_timeo.lu_reset_timeout │   WARN   │ ╭────────┬──────────╮ │
│                                         │          │ │ Actual │ Expected │ │
│                                         │          │ ├────────┼──────────┤ │
│                                         │          │ │ 30     │ 20       │ │
│                                         │          │ ╰────────┴──────────╯ │
╰─────────────────────────────────────────┴──────────┴───────────────────────╯

MULTIPATH BLACKLIST                                                 
╭──────────────────────────┬──────────┬────────────────────────────╮
│ Check                    │  Status  │ Output                     │
├──────────────────────────┼──────────┼────────────────────────────┤
│ defaults.checker_timeout │   FAIL   │ ╭────────┬──────────╮      │
│                          │          │ │ Actual │ Expected │      │
│                          │          │ ├────────┼──────────┤      │
│                          │          │ │ unset  │ 15       │      │
│                          │          │ ╰────────┴──────────╯      │
├──────────────────────────┼──────────┼────────────────────────────┤
│ Multipath blacklist      │   WARN   │ no wwid/devnode entries    │
├──────────────────────────┼──────────┼────────────────────────────┤
│ NETAPP multipath device  │   WARN   │ device block not found     │
├──────────────────────────┼──────────┼────────────────────────────┤
│ multipath.conf content   │   INFO   │ defaults {                 │
│                          │          │     user_friendly_names no │
│                          │          │     find_multipaths yes    │
│                          │          │ }                          │
╰──────────────────────────┴──────────┴────────────────────────────╯

LVM FILTERS                                                    
╭─────────────┬──────────┬────────────────────────────────────╮
│ Check       │  Status  │ Output                             │
├─────────────┼──────────┼────────────────────────────────────┤
│ LVM filters │   WARN   │ filter and global_filter are unset │
╰─────────────┴──────────┴────────────────────────────────────╯

PF9 PACKAGES                                                               
╭────────────────────────────────┬──────────┬─────────────────────────────╮
│ Check                          │  Status  │ Output                      │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ Open vSwitch common files      │    OK    │ package: openvswitch-common │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ Open vSwitch service           │    OK    │ package: openvswitch-switch │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ OVN common files               │    OK    │ package: ovn-common         │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ OVN host                       │    OK    │ package: ovn-host           │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-cindervolume-base          │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-cindervolume-config        │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-comms                      │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-glance-role                │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-ha-slave                   │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-hostagent                  │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-ip-discovery               │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-neutron-base               │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-neutron-ovn-controller     │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-neutron-ovn-metadata-agent │    OK    │ installed                   │
├────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-ostackhost                 │    OK    │ installed                   │
╰────────────────────────────────┴──────────┴─────────────────────────────╯

PF9 SERVICES                                                                       
╭────────────────────────────────────────┬──────────┬─────────────────────────────╮
│ Check                                  │  Status  │ Output                      │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-ostackhost.service                 │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-cindervolume-base.service          │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-glance-api.service                 │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-comms.service                      │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-ha-slave.service                   │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-hostagent.service                  │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-libvirt-exporter.service           │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-neutron-ovn-metadata-agent.service │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-node-exporter.service              │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-novncproxy.service                 │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-prometheus.service                 │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-remote-write.service               │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ pf9-sidekick.service                   │    OK    │ running                     │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ nova volume_use_multipath              │    OK    │ volume_use_multipath = true │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ nova_override.conf content             │   INFO   │                             │
│                                        │          │ volume_use_multipath = true │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ Libvirt VM inventory                   │   INFO   │ XML only: none              │
│                                        │          │ virsh only: none            │
│                                        │          │ local XML configs: 3        │
│                                        │          │ virsh domains: 3            │
├────────────────────────────────────────┼──────────┼─────────────────────────────┤
│ cinder_override.conf                   │   WARN   │ missing or unreadable       │
╰────────────────────────────────────────┴──────────┴─────────────────────────────╯

OVS BRIDGES                                                                                                                                                                                          
╭────────────────────┬──────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check              │  Status  │ Output                                                                                                                                                            │
├────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ OVS bridge br-int  │   WARN   │ IP: none                                                                                                                                                          │
│                    │          │ Ports: ovn-ad3e7a-0, patch-br-int-to-provnet-57216b63-846a-4ffa-aa99-7997a95dff84, tap2a95ee12-9d, tap36a2e0e8-cc, tap4c985d22-b0, tape395270c-00, tapf967d8cc-24 │
├────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ OVS bridge br-phy1 │    OK    │ IP: 10.10.12.245/18                                                                                                                                               │
│                    │          │ Ports: ens3                                                                                                                                                       │
╰────────────────────┴──────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

/ETC/HOSTS ENTRIES                                                                                             
╭────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────╮
│ Check      │  Status  │ Output                                                                              │
├────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ /etc/hosts │   INFO   │ Review required host mappings, including storage SVM IP/FQDN records.               │
│            │          │                                                                                     │
│            │          │ 127.0.1.1   test-pf9-testbed-only-5305247-260-1 test-pf9-testbed-only-5305247-260-1 │
│            │          │ 127.0.0.1 localhost                                                                 │
│            │          │                                                                                     │
│            │          │ # The following lines are desirable for IPv6 capable hosts                          │
│            │          │ ::1 ip6-localhost ip6-loopback                                                      │
│            │          │ fe00::0 ip6-localnet                                                                │
│            │          │ ff00::0 ip6-mcastprefix                                                             │
│            │          │ ff02::1 ip6-allnodes                                                                │
│            │          │ ff02::2 ip6-allrouters                                                              │
│            │          │ ff02::3 ip6-allhosts                                                                │
│            │          │ 127.0.0.1 placement-api.test-du-testbed-only-5305247-syd.svc.cluster.local          │
│            │          │ 127.0.0.1 glance-api.test-du-testbed-only-5305247-syd.svc.cluster.local             │
│            │          │ 127.0.0.1 neutron-server.test-du-testbed-only-5305247-syd.svc.cluster.local         │
│            │          │ 127.0.0.1 nova-api.test-du-testbed-only-5305247-syd.svc.cluster.local               │
│            │          │ 127.0.0.1 barbican-api.test-du-testbed-only-5305247-syd.svc.cluster.local           │
│            │          │ 127.0.0.1 cinder-api.test-du-testbed-only-5305247-syd.svc.cluster.local             │
│            │          │ 10.9.1.208 PF9-SELECT                                                               │
╰────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────╯

/ETC/FSTAB ENTRIES                                                                                                                            
╭────────────┬──────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check      │  Status  │ Output                                                                                                             │
├────────────┼──────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ /etc/fstab │    OK    │ LABEL=cloudimg-rootfs   /        ext4   discard,commit=30,errors=remount-ro     0 1                                │
│            │          │ LABEL=BOOT      /boot   ext4    defaults        0 2                                                                │
│            │          │ LABEL=UEFI      /boot/efi       vfat    umask=0077      0 1                                                        │
│            │          │ 10.10.12.12:/opt/data/instances /opt/data/instances/ nfs vers=3,proto=tcp,lookupcache=pos,nolock,noacl,_netdev 0 0 │
│            │          │ 10.10.12.12:/mnt/glance /var/opt/imagelibrary/data nfs vers=3,proto=tcp,lookupcache=pos,_netdev 0 0                │
╰────────────┴──────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

VIRSH LIVENESS                                                         
╭──────────────────────┬──────────┬───────────────────────────────────╮
│ Check                │  Status  │ Output                            │
├──────────────────────┼──────────┼───────────────────────────────────┤
│ Virsh responsiveness │    OK    │ virsh responded within 10 seconds │
╰──────────────────────┴──────────┴───────────────────────────────────╯

GROUP CONSISTENCY                                       
╭────────────────┬──────────┬──────────────────────────╮
│ Check          │  Status  │ Output                   │
├────────────────┼──────────┼──────────────────────────┤
│ Group database │    OK    │ consistency check passed │
╰────────────────┴──────────┴──────────────────────────╯

RSYSLOG PF9 RULES                                                                              
╭─────────────────────────────────────────────────┬──────────┬────────────────────────────────╮
│ Check                                           │  Status  │ Output                         │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/ostackhost.log                     │   WARN   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/cindervolume-base.log              │   WARN   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/hostagent.log                      │   WARN   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/glance-api.log                     │   WARN   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/novncproxy.log                     │   WARN   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/pf9-neutron-ovn-metadata-agent.log │   WARN   │ not found under /etc/rsyslog.d │
╰─────────────────────────────────────────────────┴──────────┴────────────────────────────────╯

PF9 USER AND GROUP                                                                          
╭───────────┬──────────┬───────────────────────────────────────────────────────────────────╮
│ Check     │  Status  │ Output                                                            │
├───────────┼──────────┼───────────────────────────────────────────────────────────────────┤
│ PF9 user  │    OK    │ name=pf9, uid=1001, gid=1001, home=/opt/pf9/home, shell=/bin/bash │
├───────────┼──────────┼───────────────────────────────────────────────────────────────────┤
│ PF9 group │    OK    │ name=pf9group, gid=1001, members=pf9, root, libvirt-qemu          │
╰───────────┴──────────┴───────────────────────────────────────────────────────────────────╯

VIRTUALIZATION AND KVM                                            
╭──────────────────────────┬──────────┬──────────────────────────╮
│ Check                    │  Status  │ Output                   │
├──────────────────────────┼──────────┼──────────────────────────┤
│ CPU virtualization flags │    OK    │ vmx/svm present          │
├──────────────────────────┼──────────┼──────────────────────────┤
│ /dev/kvm                 │    OK    │ character device present │
├──────────────────────────┼──────────┼──────────────────────────┤
│ libvirtd                 │    OK    │ active                   │
╰──────────────────────────┴──────────┴──────────────────────────╯

KERNEL COMMAND LINE                                                                                                                                                                                                                        
╭──────────────────────────┬──────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check                    │  Status  │ Output                                                                                                                                                                                            │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ IOMMU enabled on cmdline │    OK    │ intel_iommu=on                                                                                                                                                                                    │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ iommu=pt                 │    OK    │ iommu=pt                                                                                                                                                                                          │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ isolcpus                 │    OK    │ isolcpus=managed_irq,domain,2-3,6-7                                                                                                                                                               │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ nohz_full                │    OK    │ nohz_full=2-3,6-7                                                                                                                                                                                 │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ rcu_nocbs                │    OK    │ rcu_nocbs=2-3,6-7                                                                                                                                                                                 │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Hugepage parameters      │    OK    │ default_hugepagesz=2M                                                                                                                                                                             │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Kernel command line      │   INFO   │ BOOT_IMAGE=/vmlinuz-6.8.0-147-generic root=UUID=9e367d2b-90cc-4fb8-a760-383572199c1a ro intel_iommu=on iommu=pt default_hugepagesz=2M hugepagesz=2M hugepages=2048                                │
│                          │          │ isolcpus=managed_irq,domain,2-3,6-7 nohz_full=2-3,6-7 rcu_nocbs=2-3,6-7 console=tty1 console=ttyS0                                                                                                │
╰──────────────────────────┴──────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

CPU ISOLATION                                       
╭─────────────────────┬──────────┬─────────────────╮
│ Check               │  Status  │ Output          │
├─────────────────────┼──────────┼─────────────────┤
│ Isolated CPUs       │   INFO   │ 2-3,6-7         │
├─────────────────────┼──────────┼─────────────────┤
│ nohz_full CPUs      │   INFO   │ 2-3,6-7         │
├─────────────────────┼──────────┼─────────────────┤
│ Online CPUs         │   INFO   │ 0-7             │
├─────────────────────┼──────────┼─────────────────┤
│ SMT active          │   INFO   │ 0               │
├─────────────────────┼──────────┼─────────────────┤
│ SMT sibling pairing │    OK    │ check completed │
╰─────────────────────┴──────────┴─────────────────╯

CURRENT HUGEPAGE ALLOCATION                                                                                      
╭──────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────╮
│ Check                    │  Status  │ Output                                                                  │
├──────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
│ Hugepage allocation      │   INFO   │ HugePages_Total:    2048                                                │
│                          │          │ HugePages_Free:     2048                                                │
│                          │          │ HugePages_Rsvd:        0                                                │
│                          │          │ HugePages_Surp:        0                                                │
│                          │          │ Hugepagesize:       2048 kB                                             │
│                          │          │ Hugetlb:         4194304 kB                                             │
├──────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
│ hugetlbfs mount          │    OK    │ TARGET         SOURCE    FSTYPE    OPTIONS                              │
│                          │          │ /dev/hugepages hugetlbfs hugetlbfs rw,nosuid,nodev,relatime,pagesize=2M │
├──────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────┤
│ NUMA hugepage allocation │   INFO   │ Node 0:                                                                 │
│                          │          │ 4KiB: 211084                                                            │
│                          │          │ 2048KiB: 2048                                                           │
│                          │          │ 1048576KiB: 0                                                           │
╰──────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────╯

IRQ PLACEMENT                                                                             
╭───────────────────────────────┬──────────┬─────────────────────────────────────────────╮
│ Check                         │  Status  │ Output                                      │
├───────────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ irqbalance                    │    OK    │ active                                      │
├───────────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ IRQBALANCE_BANNED_CPU         │    OK    │ IRQBALANCE_BANNED_CPULIST=2-3,6-7           │
├───────────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ IRQ affinity on isolated CPUs │   INFO   │ IRQ 39: 2                                   │
│                               │          │ IRQ 40: 3                                   │
│                               │          │ IRQ 43: 6                                   │
│                               │          │ IRQ 44: 7                                   │
├───────────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ Processes on isolated CPUs    │   INFO   │ CORE   PPID     PID      PROCESS            │
│                               │          │ 2      2        30       cpuhp/2            │
│                               │          │ 2      2        31       idle_inject/2      │
│                               │          │ 2      2        32       migration/2        │
│                               │          │ 2      2        33       ksoftirqd/2        │
│                               │          │ 2      2        34       kworker/2:0-events │
│                               │          │ 3      2        37       cpuhp/3            │
│                               │          │ 3      2        38       idle_inject/3      │
│                               │          │ 3      2        39       migration/3        │
│                               │          │ 3      2        40       ksoftirqd/3        │
│                               │          │ 3      2        41       kworker/3:0-events │
│                               │          │ 6      2        59       cpuhp/6            │
│                               │          │ 6      2        60       idle_inject/6      │
│                               │          │ 6      2        61       migration/6        │
│                               │          │ 6      2        62       ksoftirqd/6        │
│                               │          │ 6      2        63       kworker/6:0-events │
│                               │          │ 7      2        66       cpuhp/7            │
│                               │          │ 7      2        67       idle_inject/7      │
│                               │          │ 7      2        68       migration/7        │
│                               │          │ 7      2        69       ksoftirqd/7        │
│                               │          │ 7      2        70       kworker/7:0-events │
╰───────────────────────────────┴──────────┴─────────────────────────────────────────────╯

NIC PASSTHROUGH CONFIGURATION                                                                                                           
╭─────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check               │  Status  │ Output                                                                                              │
├─────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ IOMMU groups        │    OK    │ 13 group(s) found                                                                                   │
├─────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ driverctl overrides │   INFO   │ 0000:01:00.0 vfio-pci                                                                               │
├─────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ vfio-pci devices    │   INFO   │ 01:00.0 Ethernet controller [0200]: Intel Corporation 82574L Gigabit Network Connection [8086:10d3] │
│                     │          │         Subsystem: Intel Corporation 82574L Gigabit Network Connection [8086:0000]                  │
│                     │          │         Kernel driver in use: vfio-pci                                                              │
│                     │          │         Kernel modules: e1000e                                                                      │
├─────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ vfio_pci module     │    OK    │ loaded                                                                                              │
╰─────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────╯

NOVA CPU AND PASSTHROUGH CONFIGURATION                                                                                                                           
╭──────────────────────────────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check                                            │  Status  │ Output                                                                                          │
├──────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ cpu_dedicated_set                                │   INFO   │ 2-3,6-7                                                                                         │
├──────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ cpu_shared_set                                   │   INFO   │ 1,5                                                                                             │
├──────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ reserved_host_memory_mb                          │   INFO   │ 4096                                                                                            │
├──────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PCI aliases, device specs, or reserved hugepages │   INFO   │ device_spec = {"address": "0000:01:00.0"}                                                       │
│                                                  │          │ alias = {"vendor_id":"8086", "product_id":"10d3", "device_type":"type-PCI", "name":"82574L-pt"} │
╰──────────────────────────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────────────────╯
```
- Actual FC relationship output when the local ports and FCP targets are online:
```
FC PORTS
╭─────────────┬────────┬──────────────────────────────────────────────────────────╮
│ Check       │ Status │ Output                                                   │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ host2       │   OK   │ WWPN: 0x100000109b123456; WWNN: 0x200000109b123456;      │
│             │        │ Port State: Online; Speed: 32 Gbit;                      │
│             │        │ Fabric Name: 0x100050eb1a2b3c4d                          │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ host3       │   OK   │ WWPN: 0x100000109b123457; WWNN: 0x200000109b123457;      │
│             │        │ Port State: Online; Speed: 32 Gbit;                      │
│             │        │ Fabric Name: 0x100050eb1a2b3c4d                          │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ rport-2:0-1 │   OK   │ Local Host: host2; Local WWPN: 0x100000109b123456;       │
│             │        │ Local State: Online; Target WWPN: 0x50060e8012345601;    │
│             │        │ Remote Role: FCP Target                                  │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ rport-2:0-2 │   OK   │ Local Host: host2; Local WWPN: 0x100000109b123456;       │
│             │        │ Local State: Online; Target WWPN: 0x50060e8012345602;    │
│             │        │ Remote Role: FCP Target                                  │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ rport-3:0-1 │   OK   │ Local Host: host3; Local WWPN: 0x100000109b123457;       │
│             │        │ Local State: Online; Target WWPN: 0x50060e8012345701;    │
│             │        │ Remote Role: FCP Target                                  │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ rport-3:0-2 │   OK   │ Local Host: host3; Local WWPN: 0x100000109b123457;       │
│             │        │ Local State: Online; Target WWPN: 0x50060e8012345702;    │
│             │        │ Remote Role: FCP Target                                  │
├─────────────┼────────┼──────────────────────────────────────────────────────────┤
│ FCP targets │   OK   │ FCP target ports visible: 4 across 2 online local FC     │
│             │        │ port(s); host2: 2 target(s); host3: 2 target(s)          │
╰─────────────┴────────┴──────────────────────────────────────────────────────────╯
```

The `rport-*` rows above are the relationship records printed by the script. Each row identifies the local host and WWPN, local state, target WWPN, and remote role. Terminal, plain-text, PDF, and JSON reports preserve this same output.

When the node has no local FC ports, the section instead reports:

```
FC PORTS
╭──────────────────────────────────────────────────────────────────────────╮
│ Check    │ Status │ Output                                               │
├──────────┼────────┼──────────────────────────────────────────────────────┤
│ FC ports │  WARN  │ no FC ports found on this node                       │
│          │        │ (/sys/class/fc_host/host* absent)                    │
╰──────────┴────────┴──────────────────────────────────────────────────────╯
```
