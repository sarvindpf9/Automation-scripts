variable "proxmox_url" {
  description = "Proxmox API URL (e.g., https://192.168.1.100:8006)"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token (format: USER@REALM!TOKEN_ID=SECRET)"
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "Skip TLS verification (set false for production with valid certs)"
  type        = bool
  default     = true
}

variable "proxmox_ssh_username" {
  description = "SSH username for Proxmox node (used for snippet file uploads)"
  type        = string
  default     = "root"
}

variable "proxmox_ssh_password" {
  description = "SSH password for Proxmox node (used for snippet file uploads)"
  type        = string
  sensitive   = true
}

variable "proxmox_node" {
  description = "Proxmox node name (e.g., pve-homelab)"
  type        = string
}

variable "template_vm_id" {
  description = "VM ID of the Ubuntu 24 template"
  type        = number
  default     = 9000
}

variable "datastore_id" {
  description = "Proxmox datastore for VM disk storage"
  type        = string
  default     = "local-1TB"
}

variable "snippet_datastore_id" {
  description = "Proxmox datastore for cloud-init snippets (must have snippets content type enabled)"
  type        = string
  default     = "local"
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key for VM access"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "vms" {
  description = "VM deployment configuration map"
  type = map(object({
    vm_name      = string
    vm_id        = number
    memory_mb    = number
    cores        = number
    sockets      = number
    disk_size_gb = optional(number, 50)

    # List of NICs in PCI slot order — first entry is primary (default route)
    network_interfaces = list(object({
      bridge  = string
      vlan_id = optional(number)  # omit or set null for untagged port
      ip      = optional(string) # omit or set null for trunk ports (VLAN-only NICs)
      gw      = optional(string)
      dns     = optional(list(string))
      vlan_devices = optional(list(object({
        id  = number
        ip  = string
        gw  = optional(string)
      })), [])
    }))
  }))
  
  validation {
    condition = alltrue([
      for vm in var.vms : vm.vm_id >= 100 && vm.vm_id <= 999999
    ])
    error_message = "VM IDs must be between 100 and 999999."
  }

  validation {
    condition = alltrue([
      for vm in var.vms : vm.cores >= 1 && vm.cores <= 80
    ])
    error_message = "Cores must be between 1 and 128."
  }

  validation {
    condition = alltrue([
      for vm in var.vms : vm.memory_mb >= 512 && vm.memory_mb <= 32768
    ])
    error_message = "Memory must be between 512MB and 32768MB (32GB)."
  }
}