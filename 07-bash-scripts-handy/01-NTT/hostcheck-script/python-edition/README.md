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
- Host utilities used by individual checks, including `ip`, `timedatectl`, `systemctl`, `grpck`, `getent`, `iscsiadm`, `multipath`, `ovs-vsctl`, `virsh`, `readlink`, and `stat`
- Root or equivalent read access is recommended because the checks inspect system, Platform9, libvirt, multipath, iSCSI, sudoers, account, `/etc/hosts`, and `/etc/fstab` data

**What it does:**

1. Detects the operating system and selects Debian or RPM package queries.
2. Runs the full host-check suite, selected standalone storage checks, or a single VM check.
3. Displays each result as `OK`, `WARN`, `FAIL`, `INFO`, or `ERROR` in a Rich terminal table.
4. Prints `/etc/hosts` and `/etc/fstab`, reports an unset LVM `filter`/`global_filter` as a warning, and checks the Open vSwitch/OVN packages or command providers required by the host checks.
5. Detects dedicated CPU or hugepage parameters in `/proc/cmdline` and conditionally runs the kernel command-line, CPU-isolation, hugepage-allocation, and IRQ-placement checks. When no matching parameter exists, each section reports that no dedicated CPU or memory configuration was found.
6. Runs the NIC-passthrough checks when `vfio_pci` is loaded; otherwise, the section reports that no NIC passthrough settings are configured.
7. Optionally creates timestamped plain-text, PDF, and JSON reports containing the same sections displayed in the terminal.

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
| `check-sudoers` | No | Adds the passwordless-sudo scan to the full default suite. |
| `check-mpath-orphan` | No | Runs the standalone multipath-orphan check. |
| `list-vm-mpath` | No | Runs the standalone per-VM multipath check. |
| `check-glance-mount` | No | Runs the standalone Glance mount check. It accepts an optional positional directory or `--glance-mount-dir`. |
| `--glance-mount-dir <DIRECTORY>` | No | Sets the Glance mount directory. The default is `/var/opt/imagelibrary`. |
| `--uuid <VM_UUID>` | No | Runs the single-VM libvirt and multipath check when no standalone storage selector is present. |
| `--resource-isolate-settings` | No | Runs only the CPU, hugepage, IRQ, KVM, NIC-passthrough, and Nova resource-isolation report. |
| `--all-optional` | No | Runs all optional storage checks and the complete resource-isolation report, excluding the passwordless-sudo listing. |
| `--log` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.log` in the current directory. Mutually exclusive with `--output`. |
| `--output <FILE>` | No | Writes a timestamped plain-text report derived from `FILE`. Mutually exclusive with `--log`. |
| `--pdf` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.pdf`. Requires `reportlab`. |
| `--json` | No | Writes `hostcheck-<short-hostname>-<YYYYMMDD_HHMMSS>.json`. |

Standalone selectors take precedence over `--uuid` and the full suite. Multiple standalone selectors can be supplied together. `--resource-isolate-settings` runs only its specific report. `--all-optional` includes the standalone storage checks and the complete resource-isolation report in the full suite. `--pdf` and `--json` can be combined with terminal-only output, `--log`, or `--output`; every requested format receives the same collected check sections.

### Output and exit behaviour

- Requested report filenames receive a `-<YYYYMMDD_HHMMSS>` suffix before their extension.
- A successful run returns `0` only when no check reports `FAIL` or `ERROR`.
- A completed report containing at least one `FAIL` or `ERROR` returns `1`.
- Initialization, report-writing, and dependency errors return `2`.
- An unset LVM `filter` and `global_filter` is reported as `WARN`; a missing or unreadable `/etc/lvm/lvm.conf` remains `FAIL`.
- `/etc/fstab` is included in the default report. An unreadable file is reported as `FAIL`.
- The default suite conditionally includes resource-isolation sections based on `/proc/cmdline` and the loaded `vfio_pci` module. Skipped sections remain visible with an `INFO` result explaining why they were skipped.
- `--all-optional` includes the complete resource-isolation report. Terminal, plain-text, PDF, and JSON outputs receive the same report collection, including skip messages and the process-column header in `Processes on isolated CPUs`.

### Sensitive output

Terminal and generated reports can expose infrastructure and account details. Store report files with access controls appropriate for operational data, and redact them before external sharing.

### Example outputs:
- help section output:
```
./hostinfo_check -h
usage: hostinfo_check.py [-h] [--uuid UUID] [--all-optional]
                         [--resource-isolate-settings]
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
╭──────────────┬─────────────────────────╮
│ Host Name    │ Report Time             │
├──────────────┼─────────────────────────┤
│ hl-u24-host3 │ 2026-10-16 12:58:28 UTC │
╰──────────────┴─────────────────────────╯

ENVIRONMENT                                         
╭──────────────────┬──────────┬────────────────────╮
│ Check            │  Status  │ Output             │
├──────────────────┼──────────┼────────────────────┤
│ Operating system │    OK    │ Ubuntu 24.04.5 LTS │
╰──────────────────┴──────────┴────────────────────╯

MULTIPATH ORPHANS                                            
╭───────────────────┬──────────┬────────────────────────────╮
│ Check             │  Status  │ Output                     │
├───────────────────┼──────────┼────────────────────────────┤
│ Multipath orphans │   WARN   │ no multipath devices found │
╰───────────────────┴──────────┴────────────────────────────╯

VM DISK MULTIPATH                                
╭───────────────────┬──────────┬────────────────╮
│ Check             │  Status  │ Output         │
├───────────────────┼──────────┼────────────────┤
│ VM disk multipath │   INFO   │ no running VMs │
╰───────────────────┴──────────┴────────────────╯

GLANCE IMAGE MOUNT                                                       
╭──────────────────────────┬──────────┬─────────────────────────────────╮
│ Check                    │  Status  │ Output                          │
├──────────────────────────┼──────────┼─────────────────────────────────┤
│ Glance mount mapping     │    OK    │ /var/opt/imagelibrary/data      │
├──────────────────────────┼──────────┼─────────────────────────────────┤
│ Glance mount permissions │   FAIL   │ ╭────────┬──────────╮           │
│                          │          │ │ Actual │ Expected │           │
│                          │          │ ├────────┼──────────┤           │
│                          │          │ │ 755    │ 744      │           │
│                          │          │ ╰────────┴──────────╯           │
├──────────────────────────┼──────────┼─────────────────────────────────┤
│ Glance mount ownership   │    OK    │ ╭──────────────┬──────────────╮ │
│                          │          │ │ Actual       │ Expected     │ │
│                          │          │ ├──────────────┼──────────────┤ │
│                          │          │ │ pf9:pf9group │ pf9:pf9group │ │
│                          │          │ ╰──────────────┴──────────────╯ │
╰──────────────────────────┴──────────┴─────────────────────────────────╯

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

ISCSI INITIATOR                                                            
╭──────────────────────┬──────────┬───────────────────────────────────────╮
│ Check                │  Status  │ Output                                │
├──────────────────────┼──────────┼───────────────────────────────────────┤
│ iSCSI initiator name │    OK    │ iqn.2004-10.com.ubuntu:01:6c7b5567883 │
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
╭──────────────────────────┬──────────┬─────────────────────────────╮
│ Check                    │  Status  │ Output                      │
├──────────────────────────┼──────────┼─────────────────────────────┤
│ defaults.checker_timeout │   FAIL   │ ╭────────┬──────────╮       │
│                          │          │ │ Actual │ Expected │       │
│                          │          │ ├────────┼──────────┤       │
│                          │          │ │ unset  │ 15       │       │
│                          │          │ ╰────────┴──────────╯       │
├──────────────────────────┼──────────┼─────────────────────────────┤
│ Multipath blacklist      │   WARN   │ no wwid/devnode entries     │
├──────────────────────────┼──────────┼─────────────────────────────┤
│ NETAPP multipath device  │   WARN   │ device block not found      │
├──────────────────────────┼──────────┼─────────────────────────────┤
│ multipath.conf content   │   INFO   │ defaults {                  │
│                          │          │     user_friendly_names yes │
│                          │          │ }                           │
╰──────────────────────────┴──────────┴─────────────────────────────╯

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
│ pf9-ha-slave                   │   FAIL   │ not installed               │
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
╭────────────────────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check                                  │  Status  │ Output                                                                                          │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-ostackhost.service                 │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-cindervolume-base.service          │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-glance-api.service                 │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-comms.service                      │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-ha-slave.service                   │   WARN   │ not installed                                                                                   │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-hostagent.service                  │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-libvirt-exporter.service           │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-neutron-ovn-metadata-agent.service │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-node-exporter.service              │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-novncproxy.service                 │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-prometheus.service                 │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-remote-write.service               │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ pf9-sidekick.service                   │    OK    │ running                                                                                         │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ nova volume_use_multipath              │   WARN   │ setting is absent                                                                               │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ nova_override.conf content             │   INFO   │ [DEFAULT]                                                                                       │
│                                        │          │ reserved_host_memory_mb = 4096                                                                  │
│                                        │          │                                                                                                 │
│                                        │          │                                                                                                 │
│                                        │          │ cpu_dedicated_set = 2-3,6-7                                                                     │
│                                        │          │ cpu_shared_set    = 1,5                                                                         │
│                                        │          │                                                                                                 │
│                                        │          │                                                                                                 │
│                                        │          │ virt_type = kvm                                                                                 │
│                                        │          │                                                                                                 │
│                                        │          │                                                                                                 │
│                                        │          │ device_spec = {"address": "0000:01:00.0"}                                                       │
│                                        │          │ alias = {"vendor_id":"8086", "product_id":"10d3", "device_type":"type-PCI", "name":"82574L-pt"} │
│                                        │          │ report_in_placement = True                                                                      │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Libvirt VM inventory                   │   INFO   │ XML only: none                                                                                  │
│                                        │          │ virsh only: none                                                                                │
│                                        │          │ local XML configs: 1                                                                            │
│                                        │          │ virsh domains: 1                                                                                │
├────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ cinder_override.conf                   │   WARN   │ missing or unreadable                                                                           │
╰────────────────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────────────────╯

OVS BRIDGES                                                                          
╭────────────────────┬──────────┬───────────────────────────────────────────────────╮
│ Check              │  Status  │ Output                                            │
├────────────────────┼──────────┼───────────────────────────────────────────────────┤
│ OVS bridge br-int  │   WARN   │ IP: none                                          │
│                    │          │ Ports: ovn0-aa2a7-0, ovn0-b41f7-0, tapc622886a-a4 │
├────────────────────┼──────────┼───────────────────────────────────────────────────┤
│ OVS bridge br-phy1 │    OK    │ IP: 172.17.0.12/20                                │
│                    │          │ Ports: enp7s18                                    │
├────────────────────┼──────────┼───────────────────────────────────────────────────┤
│ OVS bridge br-phy2 │   WARN   │ IP: none                                          │
│                    │          │ Ports: enp7s19                                    │
╰────────────────────┴──────────┴───────────────────────────────────────────────────╯

/ETC/HOSTS ENTRIES                                                                                         
╭────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────╮
│ Check      │  Status  │ Output                                                                          │
├────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ /etc/hosts │   INFO   │ Review required host mappings, including storage SVM IP/FQDN records.           │
│            │          │                                                                                 │
│            │          │ # Your system has configured 'manage_etc_hosts' as True.                        │
│            │          │ # As a result, if you wish for changes to this file to persist                  │
│            │          │ # then you will need to either                                                  │
│            │          │ # a.) make changes to the master file in /etc/cloud/templates/hosts.debian.tmpl │
│            │          │ # b.) change or remove the value of 'manage_etc_hosts' in                       │
│            │          │ #     /etc/cloud/cloud.cfg or cloud-config from user-data                       │
│            │          │ #                                                                               │
│            │          │ 127.0.1.1 ubuntu24-large ubuntu24-large                                         │
│            │          │ 127.0.0.1 localhost                                                             │
│            │          │                                                                                 │
│            │          │ # The following lines are desirable for IPv6 capable hosts                      │
│            │          │ ::1 localhost ip6-localhost ip6-loopback                                        │
│            │          │ ff02::1 ip6-allnodes                                                            │
│            │          │ ff02::2 ip6-allrouters                                                          │
│            │          │ 172.17.0.31 hl-aug-ga.sa.pf9.io                                                 │
│            │          │ 127.0.0.1 placement-api.hl-aug-ga.svc.cluster.local                             │
│            │          │ 127.0.0.1 glance-api.hl-aug-ga.svc.cluster.local                                │
│            │          │ 127.0.0.1 neutron-server.hl-aug-ga.svc.cluster.local                            │
│            │          │ 127.0.0.1 nova-api.hl-aug-ga.svc.cluster.local                                  │
│            │          │ 127.0.0.1 barbican-api.hl-aug-ga.svc.cluster.local                              │
│            │          │ 127.0.0.1 cinder-api.hl-aug-ga.svc.cluster.local                                │
╰────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────╯

/ETC/FSTAB ENTRIES                                                                                               
╭────────────┬──────────┬───────────────────────────────────────────────────────────────────────────────────────╮
│ Check      │  Status  │ Output                                                                                │
├────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ /etc/fstab │    OK    │ LABEL=cloudimg-rootfs   /        ext4   discard,commit=30,errors=remount-ro     0 1   │
│            │          │ LABEL=BOOT      /boot   ext4    defaults        0 2                                   │
│            │          │ LABEL=UEFI      /boot/efi       vfat    umask=0077      0 1                           │
│            │          │                                                                                       │
│            │          │ 172.17.0.103:/mnt/nfs_exports/nfs_glance /var/opt/imagelibrary/data nfs defaults 0 0  │
│            │          │ 172.17.0.103:/mnt/nfs_exports/nfs_ephemeral /opt/data/instances  nfs defaults 0 0     │
╰────────────┴──────────┴───────────────────────────────────────────────────────────────────────────────────────╯

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
│ /var/log/pf9/ostackhost.log                     │   FAIL   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/cindervolume-base.log              │   FAIL   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/hostagent.log                      │   FAIL   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/glance-api.log                     │   FAIL   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/novncproxy.log                     │   FAIL   │ not found under /etc/rsyslog.d │
├─────────────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ /var/log/pf9/pf9-neutron-ovn-metadata-agent.log │   FAIL   │ not found under /etc/rsyslog.d │
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
╭──────────────────────────┬──────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Check                    │  Status  │ Output                                                                                                                                                                    │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ IOMMU enabled on cmdline │    OK    │ intel_iommu=on                                                                                                                                                            │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ iommu=pt                 │    OK    │ iommu=pt                                                                                                                                                                  │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ isolcpus                 │    OK    │ isolcpus=managed_irq,domain,2-3,6-7                                                                                                                                       │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ nohz_full                │    OK    │ nohz_full=2-3,6-7                                                                                                                                                         │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ rcu_nocbs                │    OK    │ rcu_nocbs=2-3,6-7                                                                                                                                                         │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Hugepage parameters      │    OK    │ default_hugepagesz=2M                                                                                                                                                     │
├──────────────────────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Kernel command line      │   INFO   │ BOOT_IMAGE=/vmlinuz-6.8.0-147-generic root=UUID=9e367d2b-90cc-4fb8-a760-383572199c1a ro intel_iommu=on iommu=pt default_hugepagesz=2M hugepagesz=2M hugepages=2048        │
│                          │          │ isolcpus=managed_irq,domain,2-3,6-7 nohz_full=2-3,6-7 rcu_nocbs=2-3,6-7 console=tty1 console=ttyS0                                                                        │
╰──────────────────────────┴──────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

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
│                          │          │ 4KiB: 176688                                                            │
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
- FC port check output:
```
FC PORTS
╭──────────────────────────────────────────────────────────────────────────╮
│ Check │ Status │ Output                                                  │
├───────┼────────┼─────────────────────────────────────────────────────────┤
│ host0 │   OK   │ WWPN: 0x100000109b123456; WWNN: 0x200000109b123456;     │
│       │        │ Port State: Online; Speed: 16 Gbit;                     │
│       │        │ Fabric Name: 0x100000051eabcdef                         │
├───────┼────────┼─────────────────────────────────────────────────────────┤
│ host1 │   OK   │ WWPN: 0x100000109b654321; WWNN: 0x200000109b654321;     │
│       │        │ Port State: Online; Speed: 16 Gbit;                     │
│       │        │ Fabric Name: 0x100000051efedcba                         │
╰───────┴────────┴─────────────────────────────────────────────────────────╯

FC PORTS
╭──────────────────────────────────────────────────────────────────────────╮
│ Check    │ Status │ Output                                               │
├──────────┼────────┼──────────────────────────────────────────────────────┤
│ FC ports │  WARN  │ no FC ports found on this node                       │
│          │        │ (/sys/class/fc_host/host* absent)                    │
╰──────────┴────────┴──────────────────────────────────────────────────────╯
```
