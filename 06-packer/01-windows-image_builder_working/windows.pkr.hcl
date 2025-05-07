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
  description = "Whether VNC viewer should not be launched."
}

variable "disk_size" {
  type    = string
  default = "15G"
}

variable "disable_hv_evmcs" {
  type        = bool
  default     = false
  description = "Disable hv-evmcs if running on AMD EPYC"
}

variable "iso_path" {
  type    = string
  default = ""
}

variable "ovmf_suffix" {
  type    = string
  default = "_4M"
}

variable "filename" {
  type        = string
  default     = "windows2k19.dd.gz"
  description = "The filename of the tarball to produce"
}

variable "is_vhdx" {
  type        = bool
  default     = false
  description = "Whether we are building using a VHDX disk."
}

variable "use_tpm" {
  type    = string
  default = ""
  description = "Whether we are building using a virtual tpm device."
}

variable "timeout" {
  type    = string
  default = "1h"
}

locals {
  baseargs = [
    ["-cpu", "host","-hv-evmcs"],
    ["-serial", "stdio"],
    ["-drive", "if=pflash,format=raw,id=ovmf_code,readonly=on,file=/usr/share/OVMF/OVMF_CODE${var.ovmf_suffix}.ms.fd"],
    ["-drive", "if=pflash,format=raw,id=ovmf_vars,file=/usr/share/OVMF/OVMF_VARS${var.ovmf_suffix}.fd"],
    ["-drive", "file=output-windows_builder/packer-windows_builder,format=raw"],
    ["-display", "vnc=:1,password=off"],
    ["-device", "qxl-vga"],
    ["-cdrom", "${var.iso_path}"],
    ["-drive", "file=drivers.iso,media=cdrom,index=3"],
    ["-boot", "d"]
  ]
  tpmargs = [
    ["-chardev", "socket,id=chrtpm,path=/tmp/swtpm/swtpm-sock"],
    ["-tpmdev", "emulator,id=tpm0,chardev=chrtpm"],
    ["-device", "tpm-tis,tpmdev=tpm0"]
  ]
  hv_evms = [
    ["-cpu", "host"],
    ["-serial", "stdio"],
    ["-drive", "if=pflash,format=raw,id=ovmf_code,readonly=on,file=/usr/share/OVMF/OVMF_CODE${var.ovmf_suffix}.ms.fd"],
    ["-drive", "if=pflash,format=raw,id=ovmf_vars,file=/usr/share/OVMF/OVMF_VARS${var.ovmf_suffix}.fd"],
    ["-drive", "file=output-windows_builder/packer-windows_builder,format=raw"],
    ["-display", "vnc=:1,password=off"],
    ["-device", "qxl-vga"],
    ["-cdrom", "${var.iso_path}"],
    ["-drive", "file=drivers.iso,media=cdrom,index=3"],
    ["-boot", "d"]
  ]
}

source "qemu" "windows_builder" {
  accelerator      = "kvm"
  boot_command     = ["<return>"]
  boot_wait        = "2s"
  communicator     = "none"
  disk_interface   = "sata"
  disk_size        = "${var.disk_size}"
  floppy_files     = ["./http/Autounattend.xml", "./http/logon.ps1", "./http/rh.cer"]
  floppy_label     = "flop"
  format           = "raw"
  headless         = "${var.headless}"
  http_directory   = "http"
  iso_checksum     = "none"
  iso_url          = "${var.iso_path}"
  machine_type     = "q35"
  memory           = "4096"
  cpus             = "2"
  net_device       = "e1000"
  qemuargs = concat(
    var.disable_hv_evmcs ? local.hv_evms : local.baseargs,
    var.use_tpm == "yes" ? local.tpmargs : []
  )
  shutdown_timeout = "${var.timeout}"
  vnc_bind_address = "127.0.0.1"
}

build {
  sources = ["source.qemu.windows_builder"]

  post-processor "shell-local" {
    inline = [
      "echo 'Syncing output-windows_builder/packer-windows_builder...'",
      "sync -f output-windows_builder/packer-windows_builder",
      "IMG_FMT=raw",
      "source scripts/setup-nbd",
      "TMP_DIR=$(mktemp -d /tmp/packer-maas-XXXX)",
      "echo 'Adding curtin-hooks to image...'",
      "mount -t ntfs $${nbd}p4 $TMP_DIR",
      "mkdir -p $TMP_DIR/curtin",
      "cp ./curtin/* $TMP_DIR/curtin/",
      "sync -f $TMP_DIR/curtin",
      "umount $TMP_DIR",
      "qemu-nbd -d $nbd",
      "rmdir $TMP_DIR",
      "echo 'converting the raw image to qcow2.'",
      "qemu-img convert -f raw -O qcow2 output-windows_builder/packer-windows_builder  output-windows_builder/packer-windows-build.qcow2",
      "rm -rf output-windows_builder/packer-windows_builder"
    ]
    inline_shebang = "/bin/bash -e"
  }

}
