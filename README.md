# Automation Scripts

A collection of scripts and automation tooling for day-to-day infrastructure operations, covering Terraform, Ansible, Python, Packer, and Bash utilities.

> **Note:** Scripts in this repo are actively maintained and subject to frequent changes. Test before use in production.

---

## Repository Structure

### [01-terraform-labs](01-terraform-labs/)

Terraform/OpenTofu lab configurations for deploying workloads on OpenStack/PCD environments.

- `01-deploy_bulk-workload` — bulk instance deployment
- `02-deploy-instance_E2E` — end-to-end single instance deployment (image, network, volume)

### [02-Ansible-scripts](02-Ansible-scripts/)

Ansible playbooks and automation for infrastructure configuration tasks.

- `README.md` — usage instructions

### [02-deploy-instance_E2E](02-deploy-instance_E2E/)

Standalone OpenTofu configuration for deploying a single Nova instance end-to-end including optional Glance image upload and Cinder volume attachment.

See the main README section below for full usage details.

### [03-python_deployment_automation](03-python_deployment_automation/)

Python scripts for OpenStack instance lifecycle management.

- `create_instance_e2e.py` — end-to-end instance creation via OpenStack SDK
- `modules/` — reusable helper modules

### [05-Other_scripts](05-Other_scripts/)

Miscellaneous automation covering MAAS, OpenStack, PCD, and KDU operations.

| Directory / Script | Purpose |
| --- | --- |
| `01-Maas_add_baremetal` | Add baremetal nodes to MAAS |
| `02-Maas_full_automation` | Full MAAS environment automation |
| `03-pcdExpress_latest` | PCD Express deployment scripts |
| `04-openstack-samples` | OpenStack API/SDK sample scripts |
| `06-KDU-deployer` | KDU deployment automation |
| `07-ansible_plays` | Supplementary Ansible plays |
| `08-Interface_cleanup_script` | Network interface cleanup |
| `09-maas_install_script-updated` | MAAS installation automation |
| `10-run-port-group-script` | Port group configuration |
| `11-get-VM-port-stat-general` | VM port statistics |
| `12-pcd-setup-local` | Local PCD environment setup |
| `13-passwordless_user-create` | Passwordless sudo user provisioning |
| `014-delete-vjb-flavors.py` | Delete VJB flavors from OpenStack |

### [08-proxmox-automation](08-proxmox-automation/)

Proxmox hypervisor automation utilities.

| Script | Purpose |
| --- | --- |
| `oneshot-uuid_reapply.sh` | Resets machine-id, DBus ID, and stale network config on cloned VMs — runs as a one-shot systemd service on first boot |
| `sample-firstboot-reset.service` | Systemd service unit definition for the machine ID reset |
| `sample-firstboot-reset.path` | Systemd path unit that triggers the reset on marker file presence |

### [06-packer](06-packer/)

Packer templates for building machine images.

- `01-windows-image_builder_working` — Windows image build pipeline with drivers

### [07-bash-scripts-handy](07-bash-scripts-handy/)

Handy Bash scripts for host-level diagnostics and health checks.

| Script | Purpose |
| --- | --- |
| `hostInfo-check.sh` | Host health checker — bond, NTP, packages, iSCSI, multipath, OVS, PF9 services, virsh VM disk/multipath |
| `ubuntu24-precheck-script.sh` | Pre-flight checks for Ubuntu 24 hosts |
| `check_orphaned-vol.sh` | Detect orphaned Cinder volumes |
| `01-NTT/vm-multipath-check.sh` | Check multipath mapping for all running VMs |
| `01-NTT/vm-mpath-check-uuid.sh` | Check multipath mapping for a specific VM by UUID |
| `02-Siemens/kvm-tuning-check-v1.sh` | Comprehensive KVM/Nova compute tuning audit — kernel variant, CPU isolation, NUMA, IRQ affinity, THP, governor, sysctl, KVM module params |
| `02-Siemens/kvm-tuning-check-v2.sh` | Quick KVM tuning checker — validates GRUB cmdline, CPU governor, energy perf, thermal daemons, I/O scheduler, huge pages, and network tuning across 9 categories |

#### hostInfo-check.sh usage

```bash
# Run all host checks
./hostInfo-check.sh <ip> [ip2 ...]

# Check a specific VM's disk and multipath mapping
./hostInfo-check.sh --uuid <vm-uuid>

# Run all checks including virsh VM
./hostInfo-check.sh --uuid <vm-uuid> <ip> [ip2 ...]
```

---

## Requirements

- **Terraform/OpenTofu** — for `01-terraform-labs` and `02-deploy-instance_E2E`
- **Python 3** + `python3-openstackclient` — for Python scripts
- **Ansible** — for playbooks in `02-Ansible-scripts` and `05-Other_scripts/07-ansible_plays`
- **Packer** — for `06-packer`
- Standard Linux tools (`ovs-vsctl`, `multipath`, `iscsiadm`, `virsh`) for `07-bash-scripts-handy`
- **systemd** — for `08-proxmox-automation` service units
