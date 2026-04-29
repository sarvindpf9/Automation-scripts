output "vm_id" {
  description = "Proxmox VM ID"
  value       = proxmox_virtual_environment_vm.vm.vm_id
}

output "vm_name" {
  description = "VM name"
  value       = proxmox_virtual_environment_vm.vm.name
}

output "primary_ip" {
  description = "Primary IP address (without CIDR), empty string if NIC has no static IP"
  value       = var.vm_config.network_interfaces[0].ip != null ? split("/", var.vm_config.network_interfaces[0].ip)[0] : ""
}

output "network_interfaces" {
  description = "All configured network interfaces with IPs"
  value = [
    for nic in var.vm_config.network_interfaces : {
      ip      = nic.ip
      bridge  = nic.bridge
      vlan_id = nic.vlan_id
      vlan_devices = nic.vlan_devices
    }
  ]
}
