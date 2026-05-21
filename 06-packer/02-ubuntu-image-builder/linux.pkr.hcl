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
  description = "Full URL or local path to the Ubuntu 24.04 LTS server ISO."
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
  description = "Must match the username defined in http/user-data."
}

variable "ssh_password" {
  type        = string
  default     = "<SSH_PASSWORD>"
  sensitive   = true
  description = "Plaintext password. Must match the hashed value in http/user-data. Use PKR_VAR_ssh_password env var — do not commit plaintext."
}

variable "ssh_timeout" {
  type        = string
  default     = "40m"
  description = "How long Packer waits for SSH after first boot. Ubuntu 24.04 autoinstall can take 15-25 min."
}

variable "output_filename" {
  type        = string
  default     = "ubuntu-24.04.qcow2"
  description = "Filename of the final compressed qcow2 image written to output-linux_builder/."
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

  # Ubuntu 24.04 subiquity autoinstall via GRUB command line.
  # 'c' opens the GRUB command prompt; we boot casper directly to avoid
  # navigating the menu blindly across ISO variants.
  boot_wait    = "5s"
  boot_command = [
    "c<wait>",
    "linux /casper/vmlinuz --- autoinstall ds='nocloud-net;s=http://{{.HTTPIP}}:{{.HTTPPort}}/'<enter><wait5>",
    "initrd /casper/initrd<enter><wait5>",
    "boot<enter>"
  ]

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

  # Upload user-supplied fstab and hosts entry files before provisioning.
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
