variable "proxmox_node" {
  description = "Proxmox node name"
  type        = string
}

variable "template_vm_id" {
  description = "VM ID of the Ubuntu 24 template"
  type        = number
}

variable "datastore_id" {
  description = "Proxmox datastore ID for VM disk storage"
  type        = string
  default     = "local-1TB"
}

variable "snippet_datastore_id" {
  description = "Proxmox datastore ID for cloud-init snippets (must support snippets content type)"
  type        = string
  default     = "local"
}

variable "vm_config" {
  description = "VM configuration object"
  type = object({
    vm_name      = string
    vm_id        = number
    memory_mb    = number
    cores        = number
    sockets      = number
    disk_size_gb = optional(number, 50)

    # List of NICs in PCI slot order — first entry is primary (default route)
    network_interfaces = list(object({
      bridge  = string
      vlan_id = optional(number) # omit or set null for untagged port
      ip_mode = optional(string) # static, dhcp, or none; inferred from ip when omitted
      ip      = optional(string) # required when ip_mode is static
      gw      = optional(string)
      dns     = optional(list(string))
      vlan_devices = optional(list(object({
        id = number
        ip = string
        gw = optional(string)
      })), [])
    }))
  })
}

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
  sensitive   = true
}

variable "proxmox_url" {
  description = "Proxmox API URL (e.g., https://192.168.1.100:8006)"
  type        = string
}

variable "proxmox_api_username" {
  description = "Proxmox API username with realm (e.g., root@pam)"
  type        = string
}

variable "proxmox_api_password" {
  description = "Proxmox API password for proxmox_api_username"
  type        = string
  sensitive   = true
}

variable "guest_agent_ip_initial_delay_seconds" {
  description = "Initial delay before querying QEMU guest agent for DHCP IP; allows templates with first-boot machine-id reset/reboot to settle"
  type        = number
  default     = 90
}

variable "guest_agent_ip_max_wait_seconds" {
  description = "Maximum time to poll QEMU guest agent for a non-loopback DHCP IPv4 address"
  type        = number
  default     = 900
}
