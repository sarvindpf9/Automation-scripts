---
name: packer-image-builder
description: "Use this skill when the user asks to create, scaffold, refine, or fix a Packer QEMU/KVM image-builder template for Windows or Linux qcow2 images. Triggers: create packer template, scaffold packer qcow2, new image builder, generate packer template for windows/linux/ubuntu/debian/rocky/alma/rhel, build custom qcow2, refine packer template."
---

# Packer Image Builder Skill

Use this skill to produce complete, repo-consistent Packer image-builder templates for QEMU/KVM. It covers Linux cloud images built with SSH provisioning and Windows images built with unattended install, VirtIO drivers, OVMF, optional TPM, and local finalize scripts.

## Source Patterns

Before writing or changing files, read the matching source pattern:

- Linux: `06-packer/02-ubuntu-image-builder/`
- Windows: `06-packer/03-sample-windows-packer/`
- Prerequisites helper: `06-packer/packer_pre_req.sh`
- README style: `.agents/skills/readme-writer/SKILL.md`

If the user provides an existing template, read that template first and preserve its local naming/style unless it is broken.

## Behavior

- Ask one focused clarifying question only when OS family or target output path is missing and cannot be inferred.
- Never invent ISO paths, checksums, usernames, passwords, product keys, driver paths, OpenStack project names, or customer values. Use placeholders such as `<ISO_URL>`, `<ISO_CHECKSUM_SHA256>`, `<SSH_USERNAME>`, `<SSH_PASSWORD>`, `<WINDOWS_ISO_PATH>`, `<WINDOWS_PRODUCT_KEY>`.
- Prefer the repo's existing directory shape and filenames over new abstractions.
- Generate a complete file set for the requested OS unless the user explicitly asks for a single-file patch.
- Do not copy generated build output, local OVMF variable files, downloaded ISOs, or real credentials into the template tree.
- After creating or changing a template directory, use the `readme-writer` skill to create or update `README.md` from the actual files.

## Intake

Ask only the first missing value that blocks correct generation:

1. OS target: Linux or Windows. For Linux, also determine Ubuntu/Debian autoinstall or RHEL/Rocky/Alma kickstart.
2. OS version: for example Ubuntu 24.04, Rocky 9, Windows Server 2022.
3. Destination directory under `06-packer/`, if the user has not provided one and no obvious next numbered directory exists.
4. Build host type: bare metal or nested VM. This affects Windows `disable_hv_evmcs`.
5. Windows only: TPM requirement. Windows 11 normally requires TPM; Windows Server usually does not unless the user requires it.
6. Linux only: package list, extra files, and users. Accept `none` or placeholders.

## Output Layouts

### Linux

```text
06-packer/<nn>-<distro>-<slug>/
|-- linux.pkr.hcl
|-- variables.pkrvars.hcl
|-- http/
|   |-- user-data
|   `-- meta-data
|-- config/
|   |-- fstab_entries.conf
|   `-- hosts_entries.conf
|-- scripts/
|   |-- provision.sh
|   `-- cleanup.sh
`-- README.md
```

For Debian or older Ubuntu installers, replace `user-data` and `meta-data` with `preseed.cfg`. For RHEL, Rocky, or Alma, replace them with `ks.cfg`.

### Windows

```text
06-packer/<nn>-windows-<slug>/
|-- windows.pkr.hcl
|-- variables.pkrvars.hcl
|-- http/
|   |-- Autounattend.xml
|   |-- logon.ps1
|   `-- rh.cer
|-- drivers/
|   `-- README.md
|-- curtin/
|   |-- curtin-hooks
|   |-- finalize
|   |-- finalize.py
|   `-- README.md
|-- scripts/
|   |-- finalize-windows-image
|   |-- setup-nbd
|   `-- swtpm
`-- README.md
```

`drivers.iso`, Windows ISOs, and OVMF variable files are prerequisites, not committed template content, unless the repo already keeps a sample placeholder and the user explicitly asks to preserve it.

## Linux Template Rules

- Use `packer.required_version >= 1.9.0` and the HashiCorp QEMU plugin.
- Keep QEMU defaults aligned with the Linux sample: `machine_type = "q35"`, VirtIO disk/network, qcow2 output, `http_directory = "http"`, SSH communicator, and `vnc_bind_address = "127.0.0.1"`.
- Use `user-data` plus empty `meta-data` for Ubuntu 20.04+ subiquity autoinstall.
- Use `preseed.cfg` only when the requested installer still supports it.
- Use `ks.cfg` for RHEL-family builds.
- `scripts/provision.sh` must use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Package installation must detect package manager (`apt-get` or `dnf`) and include `qemu-guest-agent` unless the user explicitly excludes it.
- `scripts/cleanup.sh` must remove build-time sudoers rules, SSH host keys, package caches, machine-id, cloud-init state, logs, and temporary files.
- Do not run `mount -a` for user-supplied `fstab_entries.conf`; append entries for deployed-instance boot-time use.
- Use placeholders for hashed passwords in `user-data` and explain the hash command in comments.

## Windows Template Rules

- Use the sample Windows tree as the base because the finalize flow depends on its script and curtin layout.
- Keep `communicator = "none"` unless the user explicitly asks for WinRM provisioning.
- Use raw format during install, then `scripts/finalize-windows-image` to inject curtin hooks and convert to compressed qcow2.
- Keep OVMF code read-only and OVMF vars writable. Prefer `ovmf_vars_path = "./ovmf-vars.fd"` in `variables.pkrvars.hcl` and point users to `packer_pre_req.sh` for creating it.
- Model CPU args as a local expression so nested builds can set `disable_hv_evmcs = true`.
- Model TPM args as an optional local list controlled by `enable_tpm`; require `scripts/swtpm start` before builds that enable TPM.
- Keep VirtIO driver handling explicit. If driver INF paths are unknown, leave clear placeholders and explain that the VirtIO ISO must be mounted or extracted before build.
- Do not include real product keys, passwords, domain join details, or customer hostnames in `Autounattend.xml`.

## Validation

Run local validation when the files exist:

```bash
packer fmt .
packer validate -var-file=variables.pkrvars.hcl .
```

If Packer, QEMU, or OS-specific prerequisites are missing, state exactly what could not be validated. Do not fake validation results.
