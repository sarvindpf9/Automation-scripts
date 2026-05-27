---
name: packer-image-builder
description: "Use this skill when the user asks to create, scaffold, or generate a Packer QEMU/KVM template for any OS — Windows or Linux (Ubuntu, Debian, Rocky, Alma, RHEL). Triggers: 'create packer template', 'scaffold packer qcow2', 'new image builder', 'generate packer template for ubuntu/rocky/rhel/windows', 'build custom qcow2', 'create packer linux image', 'create packer windows image', 'new linux image builder', 'new windows image builder'."
---

# Packer Image Builder Skill

Unified skill for generating complete, runnable Packer QEMU/KVM templates for both Linux and Windows. Covers bare-metal and nested-VM build hosts, manual and CI/CD pipeline execution.

---

## Behaviour

- Ask only the most-blocking unknown before producing output. Never emit multiple clarifying questions in one turn.
- Never invent ISO URLs, checksums, package lists, usernames, passwords, or driver paths. Use clearly marked placeholders: `<ISO_URL>`, `<ISO_CHECKSUM_SHA256>`, `<SSH_USERNAME>`, `<SSH_PASSWORD>`, `<WINDOWS_ISO_PATH>`, etc.
- Produce every file in the set in a single response. Do not emit one file at a time unless explicitly asked.
- After emitting all template files, invoke the `readme-writer` skill to generate `README.md` in the same directory.
- If the user provides an existing template to fix or extend, read it first — match its style and variable naming rather than imposing these defaults.

---

## Intake Questions

Ask only the blocking ones. Skip any already answered in the user's input.

1. **OS family** — Linux or Windows? If Linux: Ubuntu/Debian (autoinstall/preseed) or RHEL/Rocky/Alma (kickstart)? This is always the first question if not provided.
2. **Distro version** — e.g., Ubuntu 24.04, Rocky 9.3, Windows Server 2022. Needed for boot command and autoinstall format.
3. **Build host type** — bare metal or VM? Determines whether `disable_hv_evmcs` should default to `true`.
4. **Package list** (Linux only) — what packages beyond base OS? Accept "none" or "I'll fill it in."
5. **TPM required?** (Windows only) — needed for Windows 11; requires `swtpm` and `enable_tpm=true`.

---

## File Sets

### Linux

```
06-packer/<nn>-<distro>-<slug>/
├── linux.pkr.hcl
├── variables.pkrvars.hcl
├── http/
│   ├── user-data          # Ubuntu 20.04+ subiquity autoinstall
│   └── meta-data          # Required empty companion file for autoinstall
│   └── preseed.cfg        # Debian / Ubuntu 18.04 legacy — emit instead of user-data
│   └── ks.cfg             # RHEL/Rocky/Alma kickstart — emit instead of user-data
├── config/
│   ├── fstab_entries.conf  # Optional fstab lines appended by provision.sh
│   └── hosts_entries.conf  # Optional /etc/hosts lines appended by provision.sh
└── scripts/
    ├── provision.sh
    └── cleanup.sh
```

Emit only one autoinstall file (`user-data`+`meta-data`, `preseed.cfg`, or `ks.cfg`), never all three.

### Windows

```
06-packer/<nn>-windows-<slug>/
├── windows.pkr.hcl
├── variables.pkrvars.hcl
├── http/
│   ├── Autounattend.xml   # Unattended Windows installer answer file
│   ├── logon.ps1          # First-logon provisioning script (runs via RunOnce)
│   └── rh.cer             # Red Hat certificate for driver signing (if required)
├── drivers/
│   └── infs/
│       ├── netkvm.inf     # VirtIO network driver INF
│       └── vioscsi.inf    # VirtIO SCSI driver INF
├── drivers.iso            # VirtIO driver ISO — must be present before build
├── curtin/
│   ├── curtin-hooks       # Curtin hook scripts injected by finalize-windows-image
│   └── finalize           # Curtin finalize hook
└── scripts/
    ├── finalize-windows-image  # NBD mount, curtin inject, raw→qcow2 conversion
    ├── setup-nbd               # Binds raw image to /dev/nbd* device
    └── swtpm                   # Software TPM lifecycle manager (start/stop/status/clean)
```

---

## Canonical Templates

### Linux: `linux.pkr.hcl`

```hcl
packer {
  required_version = ">= 1.9.0"
  required_plugins {
    qemu = {
      version = "~> 1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "iso_url" {
  type        = string
  default     = "<ISO_URL>"
  description = "Full URL or local path to the installation ISO."
}

variable "iso_checksum" {
  type        = string
  default     = "sha256:<ISO_CHECKSUM_SHA256>"
  description = "ISO checksum in 'algorithm:value' format."
}

variable "disk_size" {
  type        = string
  default     = "20G"
  description = "Root disk size for the build VM."
}

variable "memory" {
  type        = number
  default     = 2048
  description = "RAM in MB allocated to the build VM."
}

variable "cpus" {
  type        = number
  default     = 2
  description = "vCPUs allocated to the build VM."
}

variable "headless" {
  type        = bool
  default     = true
  description = "Set false to open a VNC viewer during build (debugging only)."
}

variable "ssh_username" {
  type        = string
  default     = "<SSH_USERNAME>"
  description = "Must match the username defined in http/user-data (or preseed.cfg / ks.cfg)."
}

variable "ssh_password" {
  type        = string
  default     = "<SSH_PASSWORD>"
  sensitive   = true
  description = "Plaintext password matching the hashed value in http/user-data. Pass via PKR_VAR_ssh_password — do not commit plaintext."
}

variable "ssh_timeout" {
  type        = string
  default     = "40m"
  description = "How long Packer waits for SSH after first boot. Ubuntu 24.04 autoinstall can take 15-25 min."
}

variable "output_filename" {
  type        = string
  default     = "<DISTRO>-<SLUG>-<VERSION>.qcow2"
  description = "Filename of the final compressed qcow2 image in output-linux_builder/."
}

# ── Locals ─────────────────────────────────────────────────────────────────────

locals {
  # Replace with the correct boot_command for the target distro.
  # See the Distro-Specific Boot Commands section.
  boot_command = ["<BOOT_COMMAND_PLACEHOLDER>"]
}

# ── Source ─────────────────────────────────────────────────────────────────────

source "qemu" "linux_builder" {
  accelerator    = "kvm"
  machine_type   = "q35"
  cpus           = var.cpus
  memory         = var.memory
  disk_size      = var.disk_size
  disk_interface = "virtio"
  net_device     = "virtio-net"
  format         = "qcow2"
  headless       = var.headless

  iso_url        = var.iso_url
  iso_checksum   = var.iso_checksum
  http_directory = "http"

  boot_wait    = "5s"
  boot_command = local.boot_command

  communicator     = "ssh"
  ssh_username     = var.ssh_username
  ssh_password     = var.ssh_password
  ssh_timeout      = var.ssh_timeout
  shutdown_command = "echo '${var.ssh_password}' | sudo -S shutdown -P now"

  vnc_bind_address = "127.0.0.1"
}

# ── Build ──────────────────────────────────────────────────────────────────────

build {
  sources = ["source.qemu.linux_builder"]

  provisioner "file" {
    source      = "config/fstab_entries.conf"
    destination = "/tmp/fstab_entries.conf"
  }

  provisioner "file" {
    source      = "config/hosts_entries.conf"
    destination = "/tmp/hosts_entries.conf"
  }

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | sudo -S bash -c '{{ .Path }}'"
    script          = "scripts/provision.sh"
  }

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | sudo -S bash -c '{{ .Path }}'"
    script          = "scripts/cleanup.sh"
  }

  post-processor "shell-local" {
    inline = [
      "echo 'Converting to compressed qcow2...'",
      "qemu-img convert -f qcow2 -O qcow2 -c output-linux_builder/packer-linux_builder output-linux_builder/${var.output_filename}",
      "rm -f output-linux_builder/packer-linux_builder",
      "echo 'Build complete: output-linux_builder/${var.output_filename}'"
    ]
    inline_shebang = "/bin/bash -e"
  }
}
```

---

### Linux: `variables.pkrvars.hcl`

```hcl
# ── ISO source ──────────────────────────────────────────────────────────────────
iso_url      = "<ISO_URL>"
iso_checksum = "sha256:<ISO_CHECKSUM_SHA256>"

# ── Build VM resources ──────────────────────────────────────────────────────────
disk_size = "20G"
memory    = 2048
cpus      = 2
headless  = true

# ── SSH credentials ─────────────────────────────────────────────────────────────
# ssh_username must match the username in http/user-data.
# ssh_password must match the hashed password in http/user-data.
# Do NOT commit real passwords. Pass via environment variable:
#   export PKR_VAR_ssh_password='your-password'
ssh_username = "<SSH_USERNAME>"
ssh_password = "<SSH_PASSWORD>"

# ── Output ──────────────────────────────────────────────────────────────────────
output_filename = "<DISTRO>-<SLUG>-<VERSION>.qcow2"
```

---

### Linux: `http/user-data` — Ubuntu 20.04+ subiquity autoinstall

```yaml
#cloud-config
autoinstall:
  version: 1
  locale: en_US.UTF-8
  keyboard:
    layout: us

  network:
    network:
      version: 2
      ethernets:
        any:
          match:
            name: "en*"
          dhcp4: true

  storage:
    layout:
      name: lvm

  identity:
    hostname: packer-build
    username: <SSH_USERNAME>
    # Generate the hash with: openssl passwd -6 '<SSH_PASSWORD>'
    # This hashed value MUST correspond to the plaintext ssh_password in variables.pkrvars.hcl.
    password: "<HASHED_PASSWORD>"

  ssh:
    install-server: true
    allow-pw: true

  packages:
    - openssh-server
    - curl

  late-commands:
    # Passwordless sudo required for Packer shell provisioners.
    # cleanup.sh removes this rule before the final image is sealed.
    - echo '<SSH_USERNAME> ALL=(ALL) NOPASSWD:ALL' > /target/etc/sudoers.d/packer
    - chmod 440 /target/etc/sudoers.d/packer
```

`http/meta-data` must exist as an empty file alongside `user-data`:

```bash
touch http/meta-data
```

---

### Linux: `http/ks.cfg` — RHEL / Rocky / Alma 8+

```cfg
text
lang en_US.UTF-8
keyboard us
timezone UTC --utc
network --bootproto=dhcp --hostname=packer-build

rootpw --lock
user --name=<SSH_USERNAME> --password=<SSH_PASSWORD> --groups=wheel --gecos="Packer Build User"

clearpart --all --initlabel
autopart --type=lvm

bootloader --location=mbr

%packages
@^minimal-environment
openssh-server
curl
# <USER_PACKAGES>
%end

%post
systemctl enable sshd
echo '%wheel ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers.d/packer
%end

reboot
```

---

### Linux: `scripts/provision.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# ── Package installation ────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  apt-get update -y
  apt-get install -y \
    qemu-guest-agent \
    # <USER_PACKAGES>
    :
  apt-get clean
  systemctl enable qemu-guest-agent
elif command -v dnf &>/dev/null; then
  dnf update -y
  dnf install -y \
    qemu-guest-agent \
    # <USER_PACKAGES>
    :
  dnf clean all
  systemctl enable qemu-guest-agent
fi

# ── /etc/fstab — append user-supplied entries ───────────────────────────────────
# mount -a is NOT called. Entries are written into the image for boot-time mounting
# on deployed instances, not the build VM.
FSTAB_SRC="/tmp/fstab_entries.conf"
if [[ -f "${FSTAB_SRC}" ]]; then
  FSTAB_ENTRIES=$(grep -v '^\s*#' "${FSTAB_SRC}" | grep -v '^\s*$' || true)
  if [[ -n "${FSTAB_ENTRIES}" ]]; then
    printf '\n# ── Custom entries (appended by packer build) ─────────────────────────────\n' >> /etc/fstab
    printf '%s\n' "${FSTAB_ENTRIES}" >> /etc/fstab
    echo "fstab: appended $(echo "${FSTAB_ENTRIES}" | wc -l) entry(s)"
  fi
fi
rm -f "${FSTAB_SRC}"

# ── /etc/hosts — append user-supplied entries ───────────────────────────────────
HOSTS_SRC="/tmp/hosts_entries.conf"
if [[ -f "${HOSTS_SRC}" ]]; then
  HOSTS_ENTRIES=$(grep -v '^\s*#' "${HOSTS_SRC}" | grep -v '^\s*$' || true)
  if [[ -n "${HOSTS_ENTRIES}" ]]; then
    printf '\n# ── Custom entries (appended by packer build) ─────────────────────────────\n' >> /etc/hosts
    printf '%s\n' "${HOSTS_ENTRIES}" >> /etc/hosts
    echo "hosts: appended $(echo "${HOSTS_ENTRIES}" | wc -l) entry(s)"
  fi
fi
rm -f "${HOSTS_SRC}"
```

---

### Linux: `scripts/cleanup.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Package cache ───────────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  apt-get autoremove -y
  apt-get clean
  rm -rf /var/lib/apt/lists/*
elif command -v dnf &>/dev/null; then
  dnf clean all
  rm -rf /var/cache/dnf
fi

# ── Packer build sudoers rule — remove before image is sealed ──────────────────
rm -f /etc/sudoers.d/packer

# ── SSH host keys — removed so each deployed instance regenerates its own ──────
rm -f /etc/ssh/ssh_host_*

# ── Machine identity ────────────────────────────────────────────────────────────
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -sf /etc/machine-id /var/lib/dbus/machine-id

# ── Cloud-init state — reset so it reruns on first boot of deployed instance ───
if command -v cloud-init &>/dev/null; then
  cloud-init clean --logs
fi

# ── Logs and temporary files ────────────────────────────────────────────────────
find /var/log -type f -exec truncate -s 0 {} \;
rm -rf /tmp/* /var/tmp/*
history -c 2>/dev/null || true
cat /dev/null > /root/.bash_history

# ── Zero free space — improves qcow2 compression ratio ─────────────────────────
dd if=/dev/zero of=/EMPTY bs=1M 2>/dev/null || true
rm -f /EMPTY
sync
```

---

### Windows: `windows.pkr.hcl`

```hcl
packer {
  required_version = ">= 1.7.0"

  required_plugins {
    qemu = {
      version = "~> 1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

variable "headless" {
  type        = bool
  default     = false
  description = "Run without opening a graphical console."
}

variable "disk_size" {
  type        = string
  default     = "15G"
  description = "Windows image disk size."
}

variable "disable_hv_evmcs" {
  type        = bool
  default     = false
  description = "Disable hv-evmcs on hosts where the CPU does not support it."
}

variable "iso_path" {
  type        = string
  default     = ""
  description = "Path or URL to the Windows installation ISO."
}

variable "ovmf_suffix" {
  type        = string
  default     = "_4M"
  description = "OVMF firmware filename suffix."
}

variable "ovmf_vars_path" {
  type        = string
  default     = ""
  description = "Path to a local writable copy of OVMF_VARS. Copy from /usr/share/OVMF/OVMF_VARS<suffix>.fd before building. packer_pre_req.sh does this automatically."
}

variable "enable_tpm" {
  type        = bool
  default     = false
  description = "Attach a virtual TPM. Start scripts/swtpm before enabling this. Required for Windows 11."
}

variable "swtpm_socket_path" {
  type        = string
  default     = "/tmp/swtpm/swtpm-sock"
  description = "Socket path created by scripts/swtpm. Must match SWTPM_SOCKET_PATH if using custom swtpm paths."
}

variable "timeout" {
  type        = string
  default     = "1h"
  description = "Shutdown timeout for the Windows installer."
}

variable "output_directory" {
  type        = string
  default     = "output-windows_builder"
  description = "Directory for raw and qcow2 build artifacts."
}

variable "raw_image_name" {
  type        = string
  default     = "packer-windows_builder"
  description = "Raw image filename created by the QEMU builder."
}

variable "qcow2_image_name" {
  type        = string
  default     = "packer-windows-build.qcow2"
  description = "Final qcow2 image filename."
}

locals {
  raw_image_path   = "${var.output_directory}/${var.raw_image_name}"
  qcow2_image_path = "${var.output_directory}/${var.qcow2_image_name}"

  # hv-evmcs is a QEMU CPU feature flag — must be appended to the cpu model
  # string with a comma, not passed as a separate argument.
  # Set disable_hv_evmcs=true when building inside a nested VM.
  cpu_qemuargs = var.disable_hv_evmcs ? [["-cpu", "host"]] : [["-cpu", "host,hv-evmcs"]]

  # ovmf_vars_file resolves the local OVMF_VARS path.
  # OVMF_VARS is writable; QEMU modifies it during the build.
  # Always point at a local copy — never the shared system file.
  ovmf_vars_file = var.ovmf_vars_path != "" ? var.ovmf_vars_path : "/usr/share/OVMF/OVMF_VARS${var.ovmf_suffix}.fd"

  base_qemuargs = [
    ["-serial", "stdio"],
    ["-drive", "if=pflash,format=raw,id=ovmf_code,readonly=on,file=/usr/share/OVMF/OVMF_CODE${var.ovmf_suffix}.ms.fd"],
    ["-drive", "if=pflash,format=raw,id=ovmf_vars,file=${local.ovmf_vars_file}"],
    ["-drive", "file=${local.raw_image_path},format=raw"],
    ["-display", "vnc=:1,password=off"],
    ["-device", "qxl-vga"],
    ["-cdrom", var.iso_path],
    ["-drive", "file=drivers.iso,media=cdrom,index=3"],
    ["-boot", "d"],
  ]

  tpm_qemuargs = [
    ["-chardev", "socket,id=chrtpm,path=${var.swtpm_socket_path}"],
    ["-tpmdev", "emulator,id=tpm0,chardev=chrtpm"],
    ["-device", "tpm-tis,tpmdev=tpm0"],
  ]
}

source "qemu" "windows_builder" {
  accelerator      = "kvm"
  boot_command     = ["<return>"]
  boot_wait        = "2s"
  communicator     = "none"
  cpus             = "2"
  disk_interface   = "sata"
  disk_size        = var.disk_size
  floppy_files     = ["./http/Autounattend.xml", "./http/logon.ps1", "./http/rh.cer"]
  floppy_label     = "flop"
  format           = "raw"
  headless         = var.headless
  http_directory   = "http"
  iso_checksum     = "none"
  iso_url          = var.iso_path
  machine_type     = "q35"
  memory           = "4096"
  net_device       = "e1000"
  output_directory = var.output_directory
  qemuargs         = concat(local.cpu_qemuargs, local.base_qemuargs, var.enable_tpm ? local.tpm_qemuargs : [])
  shutdown_timeout = var.timeout
  vnc_bind_address = "127.0.0.1"
}

build {
  sources = ["source.qemu.windows_builder"]

  post-processor "shell-local" {
    inline = [
      "scripts/finalize-windows-image '${local.raw_image_path}' '${local.qcow2_image_path}'",
    ]
    inline_shebang = "/bin/bash -e"
  }
}
```

---

### Windows: `variables.pkrvars.hcl`

```hcl
iso_path          = "<WINDOWS_ISO_PATH>"
disk_size         = "15G"
headless          = false
disable_hv_evmcs  = false   # set true when building inside a nested VM
enable_tpm        = false
swtpm_socket_path = "/tmp/swtpm/swtpm-sock"
timeout           = "1h"
ovmf_vars_path    = "./ovmf-vars.fd"  # created by packer_pre_req.sh
```

---

## Host Preparation

`06-packer/packer_pre_req.sh` sets up all build-host dependencies. Run it once per host before any build:

```bash
cd 06-packer
sudo bash packer_pre_req.sh
# Log out and back in for kvm group membership to take effect.
```

**What it installs:**
- `qemu-system`, `qemu-utils`, `ovmf`, `swtpm`, `ntfs-3g`, `cloud-image-utils`, `xorriso`, `libnbd-bin`, `nbdkit`, `wimtools`, `fuse2fs`, `jq`, `ssvnc`
- `packer` from the official HashiCorp APT repo
- Adds the build user to the `kvm` group
- Copies `OVMF_VARS_4M.fd` to a local `ovmf-vars.fd` in the same directory

**After running:** set `ovmf_vars_path = "./ovmf-vars.fd"` in `variables.pkrvars.hcl` (for Windows builds). The script writes it to the `06-packer/` directory; adjust the path if your template is in a subdirectory.

**KVM access check:** if `/dev/kvm` does not exist after running the script, nested virtualisation is not enabled on the parent hypervisor. Builds will still run with `accelerator = "kvm"` on bare metal; on a VM without nested virt, change `accelerator` to `"none"` (very slow).

---

## Distro-Specific Boot Commands

Insert the correct value into `locals.boot_command` in `linux.pkr.hcl`.

### Ubuntu 24.04 (casper/GRUB CLI — preferred for 24.04 ISOs)

```hcl
boot_command = [
  "c<wait>",
  "linux /casper/vmlinuz --- autoinstall ds='nocloud-net;s=http://{{.HTTPIP}}:{{.HTTPPort}}/'<enter><wait5>",
  "initrd /casper/initrd<enter><wait5>",
  "boot<enter>"
]
```

`http/` must contain `user-data` and `meta-data` (empty file).

### Ubuntu 20.04 / 22.04 (subiquity / autoinstall)

```hcl
boot_command = [
  "<esc><wait>",
  "e<wait>",
  "<down><down><down><end>",
  " autoinstall ds=nocloud-net;s=http://{{.HTTPIP}}:{{.HTTPPort}}/<f10>"
]
```

`http/` must contain `user-data` and `meta-data`.

### Ubuntu 18.04 / Debian (legacy preseed)

```hcl
boot_command = [
  "<esc><wait>",
  "auto url=http://{{.HTTPIP}}:{{.HTTPPort}}/preseed.cfg ",
  "hostname=packer-build domain=localdomain interface=auto ",
  "DEBIAN_FRONTEND=newt<enter>"
]
```

`http/` must contain `preseed.cfg`.

### Rocky / Alma / RHEL 8+

```hcl
boot_command = [
  "<tab><wait>",
  " inst.ks=http://{{.HTTPIP}}:{{.HTTPPort}}/ks.cfg inst.cmdline<enter>"
]
```

`http/` must contain `ks.cfg`.

---

## Build Host Constraints

### Bare Metal vs Nested VM

| Setting | Bare Metal | Nested VM |
| ------- | ---------- | --------- |
| `disable_hv_evmcs` | `false` (default) | **`true`** |
| `accelerator` | `"kvm"` | `"kvm"` (requires nested virt enabled on parent) |
| Nested virt prereq | None | `modprobe kvm_intel nested=1` or parent hypervisor config |

On a nested VM, `hv-evmcs` (Hyper-V Enlightened VMCS) is a CPU feature the outer hypervisor typically does not expose to guests. QEMU will refuse to start if it is requested. Always set `disable_hv_evmcs = true` in `variables.pkrvars.hcl` when the build host is itself a VM.

**Important:** `hv-evmcs` is appended to the `-cpu` model string as a comma-separated feature (`host,hv-evmcs`), not as a separate QEMU argument. Passing it as a separate argument causes QEMU to interpret it as a CPU model name, which does not exist.

### OVMF_VARS — always use a local copy

QEMU writes UEFI boot entries, Secure Boot state, and firmware variables to the OVMF_VARS file during the build. **If you point QEMU at the system file (`/usr/share/OVMF/OVMF_VARS*.fd`), it will modify it**, corrupting the shared file and breaking all subsequent builds on that host.

`packer_pre_req.sh` copies the system file to `ovmf-vars.fd` in the `06-packer/` directory. Set `ovmf_vars_path` to this local copy in `variables.pkrvars.hcl`. If the template is in a subdirectory, copy relative to it:

```bash
cp /usr/share/OVMF/OVMF_VARS_4M.fd ./OVMF_VARS_4M.fd
```

`OVMF_CODE` is always attached read-only (`readonly=on`) from the system path — it never needs a local copy.

### QEMU floppy format warning

The packer-plugin-qemu does not pass `format=raw` on the floppy image it builds internally. QEMU >= 6.1 emits a warning about raw image format detection. This warning is non-fatal: Windows setup reads `Autounattend.xml` from the floppy without write access to block 0, so the restriction does not affect the unattended install. No workaround is required.

### VNC access

VNC is always bound to `127.0.0.1`. For remote debugging, use an SSH tunnel:

```bash
ssh -L 5901:127.0.0.1:5901 <build-host>
# then connect a VNC client to localhost:5901
```

Windows templates use display `:1` (port 5901). Linux templates use the Packer-assigned port; check `PACKER_LOG=1` output for the exact port.

---

## Pipeline Execution

For CI/CD (GitHub Actions, Jenkins, or scripted pipelines):

1. **Prerequisites step** — run `packer_pre_req.sh` as a one-time host setup or a pipeline setup job.
2. **Always headless** — set `headless = true` in `variables.pkrvars.hcl` or pass `-var headless=true`.
3. **Credentials via env vars** — never commit real passwords:
   ```bash
   export PKR_VAR_ssh_password='<value>'    # Linux
   export PKR_VAR_iso_path='/path/to.iso'   # Windows
   ```
4. **ISO checksum** — use a real `sha256:<hash>` in CI. `iso_checksum = "none"` is only acceptable for local/offline builds where the ISO is trusted.
5. **OVMF_VARS** — copy before the build step in the pipeline:
   ```bash
   cp /usr/share/OVMF/OVMF_VARS_4M.fd "${WORKSPACE}/ovmf-vars.fd"
   packer build -var "ovmf_vars_path=${WORKSPACE}/ovmf-vars.fd" ...
   ```
6. **Packer log** — set `PACKER_LOG=1` and `PACKER_LOG_PATH=packer.log` to capture QEMU stderr for build failure triage.
7. **Output artefact** — add `output-linux_builder/` and `output-windows_builder/` to `.gitignore`.

---

## Windows-Specific Nuances

### `communicator = "none"`

Windows builds do not use SSH or WinRM during the packer build phase. All provisioning happens via `Autounattend.xml` (installer) and `logon.ps1` (first-logon RunOnce). There is no in-guest Packer provisioner block.

### Two-stage raw → qcow2 conversion

The QEMU builder writes a raw disk image. After QEMU exits, `scripts/finalize-windows-image`:
1. Binds the raw image to a free `/dev/nbd*` device via `scripts/setup-nbd`.
2. Mounts partition 4 (NTFS system partition) and copies `curtin/` hooks into it.
3. Disconnects NBD and converts the raw image to qcow2 with `qemu-img convert`.
4. Removes the raw image.

Root (or sudo) is required for the NBD mount step. When running via Packer, the post-processor shell-local runs as the build user; ensure `sudo` is available without a password for that user, or run `packer build` with `sudo`.

### `drivers.iso`

`drivers.iso` must be present in the template directory before the build starts. It is attached as a CD-ROM at index 3. The ISO contains VirtIO/SCSI driver packages referenced from `http/logon.ps1` or `Autounattend.xml`. It is not built by this template — acquire it from the upstream VirtIO driver distribution.

### Sensitive data in `http/`

`http/Autounattend.xml` and `http/logon.ps1` contain the local Administrator password in plaintext. Replace the placeholder before production use and do not commit environment-specific credentials to version control.

### swtpm (Windows 11 / TPM required builds)

```bash
# Start swtpm before the packer build
scripts/swtpm start

# Build
sudo packer build -var-file=variables.pkrvars.hcl -var enable_tpm=true windows.pkr.hcl

# Stop after build completes
scripts/swtpm stop
```

The `swtpm_socket_path` variable must match `SWTPM_SOCKET_PATH` used by `scripts/swtpm`. Defaults (`/tmp/swtpm/swtpm-sock`) align without override.

---

## Naming Conventions

| Element | Linux | Windows |
| ------- | ----- | ------- |
| Directory | `06-packer/<nn>-<distro>-<slug>/` | `06-packer/<nn>-windows-<slug>/` |
| Main template | `linux.pkr.hcl` | `windows.pkr.hcl` |
| Source label | `linux_builder` | `windows_builder` |
| Output directory | `output-linux_builder/` | `output-windows_builder/` |
| Output file | `<distro>-<slug>-<version>.qcow2` | `packer-windows-build.qcow2` (or override) |
| Variable names | descriptive snake_case | descriptive snake_case |

---

## Steps Claude Must Follow

1. Confirm OS family if not provided — this is always the first question.
2. Confirm the distro/version and build host type (BM or VM).
3. **Linux:** choose the correct autoinstall file (`user-data`+`meta-data`, `preseed.cfg`, or `ks.cfg`), insert the matching `boot_command` into `locals`. Never emit more than one autoinstall format.
4. **Windows:** always emit the full `qemuargs` locals block with `cpu_qemuargs`, `base_qemuargs`, and `tpm_qemuargs`. Never collapse these into a flat list — the concat pattern is required for the `enable_tpm` conditional to work.
5. Set `disable_hv_evmcs = true` in `variables.pkrvars.hcl` if the build host is a VM.
6. Set `ovmf_vars_path = "./ovmf-vars.fd"` in `variables.pkrvars.hcl` for Windows builds (matches `packer_pre_req.sh` output path).
7. Embed the user's package list in `scripts/provision.sh` (Linux). If not provided, leave the `# <USER_PACKAGES>` placeholder.
8. Emit all files in the set as a complete response.
9. Invoke `readme-writer` to generate `README.md` in the same directory.
10. State which placeholder values remain and exactly where to set them.

---

## Hard Constraints

**Linux:**
- Never use `communicator = "none"` — Linux uses SSH provisioners.
- Never use `format = "raw"` — Linux builds qcow2 natively.
- Always use `disk_interface = "virtio"` and `net_device = "virtio-net"`.
- Never add `floppy_files` — Linux uses the HTTP server for autoinstall.
- `cleanup.sh` must always zero free space and remove SSH host keys. These are not optional.
- `machine_type = "q35"` always; never `pc`.

**Windows:**
- Always use `communicator = "none"` — no in-guest provisioner.
- Always use `format = "raw"` in the source block — raw is required for the two-stage NBD conversion.
- Always use `disk_interface = "sata"` and `net_device = "e1000"`.
- Never hardcode OVMF paths directly — always go through the `ovmf_vars_file` local which respects `ovmf_vars_path`.
- The `-cpu` feature flag for `hv-evmcs` must be comma-appended to the model string (`"host,hv-evmcs"`), never passed as a separate argument element.
- `iso_checksum = "none"` is acceptable for local Windows ISO builds (Microsoft ISOs are not publicly checksummed via a standard mechanism); use a real checksum in CI if the ISO is fetched remotely.

**Both:**
- `accelerator = "kvm"` always.
- `vnc_bind_address = "127.0.0.1"` always — never `0.0.0.0`.
- Never commit real credentials. Note in README that `variables.pkrvars.hcl` with real values should be in `.gitignore`.
- `output-linux_builder/` and `output-windows_builder/` are generated artefacts — note `.gitignore` in README.
