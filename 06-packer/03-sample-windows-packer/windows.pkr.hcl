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
  default     = "64G"
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
  description = "Path to a writable OVMF_VARS file. Defaults to ovmf-vars.fd in the parent directory, created by packer_pre_req.sh. Override only when using a custom location."
}

variable "enable_tpm" {
  type        = bool
  default     = false
  description = "Attach a virtual TPM. Start scripts/swtpm before enabling this."
}

variable "swtpm_socket_path" {
  type        = string
  default     = "/tmp/swtpm/swtpm-sock"
  description = "Socket path created by scripts/swtpm."
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
  cpu_qemuargs     = var.disable_hv_evmcs ? [["-cpu", "host"]] : [["-cpu", "host,hv-evmcs"]]
  # path.root is the directory containing this .pkr.hcl file; ../ovmf-vars.fd is
  # the writable copy created by packer_pre_req.sh one level up in 06-packer/.
  # The system file at /usr/share/OVMF/ is root-owned and read-only — QEMU needs
  # a writable VARS file to persist UEFI boot variables during the build.
  ovmf_vars_file   = var.ovmf_vars_path != "" ? var.ovmf_vars_path : "${path.root}/../ovmf-vars.fd"

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
