# Automation Scripts

A collection of scripts and automation tooling for day-to-day infrastructure operations, covering Terraform, Ansible, Python, Packer, Bash utilities, and AI agent tooling.

> **Note:** Scripts in this repo are actively maintained and subject to frequent changes. Test before use in production.

---

## Repository Structure

### [01-terraform-labs](01-terraform-labs/)

Terraform/OpenTofu lab configurations for deploying workloads on OpenStack/PCD and Proxmox environments.

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `01-deploy_bulk-workload` | Bulk OpenStack instance deployment | [README](01-terraform-labs/01-deploy_bulk-workload/README.md) |
| `02-deploy-instance_E2E` | End-to-end single instance deployment (image, network, volume) | [README](01-terraform-labs/02-deploy-instance_E2E/README.md) |
| `03-proxmox-deploy-vm` | Deploy Ubuntu 24 VMs on Proxmox VE via template clone, cloud-init, and Ansible inventory generation | [README](01-terraform-labs/03-proxmox-deploy-vm/README.md) |
| `05-NTT/multi-cluster-aggregate` | Deploy OpenStack instances pinned to a host aggregate using a private custom flavor | [README](01-terraform-labs/05-NTT/multi-cluster-aggregate/README.md) |

### [02-Ansible-scripts](02-Ansible-scripts/)

Ansible playbooks and automation for OpenStack instance management, host configuration, and platform preparation.

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `01-example_instance_E2E` | End-to-end OpenStack instance deployment via Ansible | [README](02-Ansible-scripts/01-example_instance_E2E/README.md) |
| `02-instance-deploy-rollout` | Bulk Nova instance deploy/teardown with configurable storage backend, AZ, and flavor pre-step | [README](02-Ansible-scripts/02-instance-deploy-rollout/README.md) |
| `03-prepare-CE-VMs` | Renders static netplan config for CE VMs/bare-metal, disables DHCP on a second interface, adds NFS mounts | [README](02-Ansible-scripts/03-prepare-CE-VMs/README.md) |
| `04-glance-isolated-cluster` | Configures local Glance access on PF9 hosts running `pf9-glance-api` | [README](02-Ansible-scripts/04-glance-isolated-cluster/README.md) |
| `05-host-check-templates/01-host-healthcheck` | Audits Linux host health (sysctl params, NTP), reports per-host OK/WARN without modifying state | [README](02-Ansible-scripts/05-host-check-templates/01-host-healthcheck/README.md) |
| `06-proxmox-VM-create` | Proxmox VM clone automation with cloud-init, VLAN-aware NICs, and inventory-driven VM definitions | [README](02-Ansible-scripts/06-proxmox-VM-create/README.md) |

### [02-deploy-instance_E2E](02-deploy-instance_E2E/)

Standalone OpenTofu configuration for deploying a single Nova instance end-to-end including optional Glance image upload and Cinder volume attachment.

See [README](02-deploy-instance_E2E/README.md) for usage details.

### [03-python_deployment_automation](03-python_deployment_automation/)

Python scripts for OpenStack instance lifecycle management.

- `create_instance_e2e.py` — end-to-end instance creation via OpenStack SDK
- `modules/` — reusable helper modules

See [README](03-python_deployment_automation/README.md) for usage details.

### [05-Other_scripts](05-Other_scripts/)

Miscellaneous automation covering MAAS, OpenStack, PCD, and KDU operations.

| Directory / Script | Purpose | README |
| ------------------ | ------- | ------ |
| `01-Maas_add_baremetal` | Add baremetal nodes to MAAS | [README](05-Other_scripts/01-Maas_add_baremetal/README.md) |
| `02-Maas_full_automation` | Full MAAS environment automation | [README](05-Other_scripts/02-Maas_full_automation/README.md) |
| `03-pcdExpress_latest/pcdExpress_utility` | PCD Express utility scripts and supporting automation | [README](05-Other_scripts/03-pcdExpress_latest/pcdExpress_utility/README.md) |
| `04-openstack-samples` | OpenStack API/SDK sample scripts | — |
| `06-KDU-deployer` | KDU deployment automation | — |
| `07-ansible_plays` | Supplementary Ansible plays | — |
| `08-Interface_cleanup_script` | Network interface cleanup | — |
| `09-maas_install_script-updated` | MAAS installation automation | — |
| `10-run-port-group-script` | Port group configuration | — |
| `11-get-VM-port-stat-general` | VM port statistics | — |
| `12-pcd-setup-local` | Local PCD environment setup | — |
| `13-passwordless_user-create` | Passwordless sudo user provisioning | — |
| `014-delete-vjb-flavors.py` | Delete VJB flavors from OpenStack | — |
| `14-pcdexpressV2` | PCDExpress v2 — Python-driven PCD deployment and host onboarding framework | [README](05-Other_scripts/14-pcdexpressV2/README.md) |
| `15-pcd-maas-with_proxmox_BM` | Combined PCD + MAAS + Proxmox bare-metal automation | [README](05-Other_scripts/15-pcd-maas-with_proxmox_BM/README.md) |

Additional README files:

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `02-Maas_full_automation/pcd_ansible-pcd_develop` | PCD Ansible development tree used by the MAAS automation workflow | [README](05-Other_scripts/02-Maas_full_automation/pcd_ansible-pcd_develop/README.md) |
| `02-Maas_full_automation/pcd_ansible-pcd_develop/ansible-collections-pf9` | PF9 PCD Ansible collection bundled with the MAAS automation workflow | [README](05-Other_scripts/02-Maas_full_automation/pcd_ansible-pcd_develop/ansible-collections-pf9/README.md) |
| `02-Maas_full_automation/pcd_ansible-pcd_develop/ansible-collections-pf9/plugins` | Plugin directory for the bundled PF9 PCD Ansible collection | [README](05-Other_scripts/02-Maas_full_automation/pcd_ansible-pcd_develop/ansible-collections-pf9/plugins/README.md) |
| `03-pcdExpress_latest/pcdExpress_utility/ansible-collections-pf9` | PF9 PCD Ansible collection bundled with the PCD Express utility | [README](05-Other_scripts/03-pcdExpress_latest/pcdExpress_utility/ansible-collections-pf9/README.md) |
| `03-pcdExpress_latest/pcdExpress_utility/ansible-collections-pf9/plugins` | Plugin directory for the PCD Express PF9 Ansible collection | [README](05-Other_scripts/03-pcdExpress_latest/pcdExpress_utility/ansible-collections-pf9/plugins/README.md) |
| `14-pcdexpressV2/ansible-collections-pf9` | PF9 PCD Ansible collection for PCDExpress v2 | [README](05-Other_scripts/14-pcdexpressV2/ansible-collections-pf9/README.md) |
| `14-pcdexpressV2/ansible-collections-pf9/plugins` | Plugin directory for the PCDExpress v2 PF9 Ansible collection | [README](05-Other_scripts/14-pcdexpressV2/ansible-collections-pf9/plugins/README.md) |
| `14-pcdexpressV2/plugins` | PCDExpress v2 plugin directory | [README](05-Other_scripts/14-pcdexpressV2/plugins/README.md) |
| `15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop` | PCD Ansible development tree used by the PCD + MAAS + Proxmox workflow | [README](05-Other_scripts/15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop/README.md) |
| `15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop/ansible-collections-pf9` | PF9 PCD Ansible collection bundled with the PCD + MAAS + Proxmox workflow | [README](05-Other_scripts/15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop/ansible-collections-pf9/README.md) |
| `15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop/ansible-collections-pf9/plugins` | Plugin directory for the bundled PF9 PCD Ansible collection | [README](05-Other_scripts/15-pcd-maas-with_proxmox_BM/pcd_ansible-pcd_develop/ansible-collections-pf9/plugins/README.md) |

### [06-packer](06-packer/)

Packer QEMU/KVM templates for building machine images (qcow2).

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `01-windows-image_builder_working` | Windows image build pipeline with VirtIO drivers | [curtin](06-packer/01-windows-image_builder_working/curtin/README.md), [drivers](06-packer/01-windows-image_builder_working/drivers/README.md) |
| `02-ubuntu-image-builder` | Ubuntu 24.04 LTS qcow2 golden image with `qemu-guest-agent`, custom fstab and hosts entries | [README](06-packer/02-ubuntu-image-builder/README.md) |
| `03-sample-windows-packer` | Windows qcow2 with optional swtpm (software TPM), curtin hooks, and standalone swtpm lifecycle script | [README](06-packer/03-sample-windows-packer/README.md), [curtin](06-packer/03-sample-windows-packer/curtin/README.md), [drivers](06-packer/03-sample-windows-packer/drivers/README.md) |

`packer_pre_req.sh` — installs Packer, QEMU, and swtpm prerequisites on the build host.

### [07-bash-scripts-handy](07-bash-scripts-handy/)

Handy Bash scripts for host-level diagnostics and health checks.

| Script | Purpose |
| ------ | ------- |
| `hostInfo-check.sh` | Host health checker — bond, NTP, packages, iSCSI, multipath, OVS, PF9 services, virsh VM disk/multipath |
| `ubuntu24-precheck-script.sh` | Pre-flight checks for Ubuntu 24 hosts |
| `check_orphaned-vol.sh` | Detect orphaned Cinder volumes |
| `dry_run_orphan_check.sh` | Dry-run version of orphaned volume detection |

**`01-NTT/`** — OpenStack/PCD VM provisioning and KVM multipath diagnostics — [README](07-bash-scripts-handy/01-NTT/README.md)

| Script | Purpose |
| ------ | ------- |
| `launch-VM-with-images.sh` | Launch OpenStack VMs with image attachment |
| `vm-multipath-check.sh` | Check multipath mapping for all running VMs |
| `vm-mpath-check-uuid.sh` | Check multipath mapping for a specific VM by UUID |
| `mpath-iscsi-disk-cleanup.sh` | Clean up stale iSCSI/multipath disk mappings |
| `cdrom-attach-script/` | Attach and detach virtual CD-ROM ISOs to running VMs |
| `hostcheck-script/` | Host info and health check script bundle |
| `virsh-cleanup-script/` | Clean up stale virsh domain definitions |
| `sort-uuids-virsh/` | Sort and reconcile virsh UUIDs |

Additional README files:

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `01-NTT/cdrom-attach-script` | Attach and detach virtual CD-ROM ISOs to running VMs | [README](07-bash-scripts-handy/01-NTT/cdrom-attach-script/README.md) |
| `01-NTT/hostcheck-script` | Host health, sudoers, orphaned multipath, and VM disk mapping checks | [README](07-bash-scripts-handy/01-NTT/hostcheck-script/README.md) |
| `01-NTT/mpath-iscsi-disk-cleanup.sh` | Report and clean orphaned iSCSI and multipath disk mappings | [README](07-bash-scripts-handy/01-NTT/mpath-iscsi-disk-cleanup.sh/README.md) |
| `01-NTT/virsh-cleanup-script` | Inspect VM disk mappings and clean up stale virsh domain state | [README](07-bash-scripts-handy/01-NTT/virsh-cleanup-script/README.md) |

**`02-Siemens/`** — KVM/Nova compute tuning audits — [README](07-bash-scripts-handy/02-Siemens/README.md)

| Script | Purpose |
| ------ | ------- |
| `kvm-tuning-check-v1.sh` | Comprehensive KVM/Nova tuning audit — kernel variant, CPU isolation, NUMA, IRQ affinity, THP, governor, sysctl, KVM module params |
| `kvm-tuning-check-v2.sh` | Quick KVM tuning checker — validates GRUB cmdline, CPU governor, energy perf, thermal daemons, I/O scheduler, huge pages, and network tuning across 9 categories |

Additional README files:

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `02-Siemens/02-glance-image-mapping` | Check Glance image backend mapping and image placement details | [README](07-bash-scripts-handy/02-Siemens/02-glance-image-mapping/README.md) |
| `02-Siemens/decomm-cleanup` | Decommission cleanup workflow for stale host and OpenStack artifacts | [README](07-bash-scripts-handy/02-Siemens/decomm-cleanup/README.md) |

#### hostInfo-check.sh usage

```bash
# Run all host checks
./hostInfo-check.sh <ip> [ip2 ...]

# Check a specific VM's disk and multipath mapping
./hostInfo-check.sh --uuid <vm-uuid>

# Run all checks including virsh VM
./hostInfo-check.sh --uuid <vm-uuid> <ip> [ip2 ...]
```

### [08-proxmox-automation](08-proxmox-automation/)

Proxmox hypervisor automation utilities.

| Script | Purpose |
| ------ | ------- |
| `oneshot-uuid_reapply.sh` | Resets machine-id, DBus ID, and stale network config on cloned VMs — runs as a one-shot systemd service on first boot |
| `sample-firstboot-reset.service` | Systemd service unit definition for the machine ID reset |
| `sample-firstboot-reset.path` | Systemd path unit that triggers the reset on marker file presence |

### [09-python-scripts](09-python-scripts/)

Standalone Python utilities for network and infrastructure operations.

| Script | Purpose |
| ------ | ------- |
| `free-subnet-ip-checker.py` | Scan a subnet and report free (unused) IP addresses — supports ICMP ping and TCP probing, configurable workers and timeout |

### [claude-automation](claude-automation/)

Claude and MCP-oriented automation experiments and supporting tooling.

| Directory | Purpose | README |
| --------- | ------- | ------ |
| `hackathon-mcp-sow` | Platform9 PCD MCP server and supporting docs/tools | [README](claude-automation/hackathon-mcp-sow/README.md) |

---

## Requirements

- **Terraform/OpenTofu** — for `01-terraform-labs` and `02-deploy-instance_E2E`
- **Python 3** + `python3-openstackclient` — for Python scripts
- **Ansible** — for playbooks in `02-Ansible-scripts` and `05-Other_scripts/07-ansible_plays`
- **Packer** + QEMU/KVM — for `06-packer` (run `packer_pre_req.sh` first)
- Standard Linux tools (`ovs-vsctl`, `multipath`, `iscsiadm`, `virsh`) for `07-bash-scripts-handy`
- **systemd** — for `08-proxmox-automation` service units
