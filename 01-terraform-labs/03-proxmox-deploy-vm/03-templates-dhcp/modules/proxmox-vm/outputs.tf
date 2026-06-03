output "vm_id" {
  description = "Proxmox VM ID"
  value       = proxmox_virtual_environment_vm.vm.vm_id
}

output "vm_name" {
  description = "VM name"
  value       = proxmox_virtual_environment_vm.vm.name
}

output "primary_ip" {
  description = "Primary IP address without CIDR; learned from QEMU guest agent for DHCP"
  value = (
    local.network_interfaces[0].effective_ip_mode == "dhcp"
    ? try(
      jsondecode(data.local_file.primary_ip[0].content).primary_ip,
      try([
        for ip in flatten(proxmox_virtual_environment_vm.vm.ipv4_addresses) : ip
        if !startswith(ip, "127.") && !startswith(ip, "169.254.") && ip != "0.0.0.0"
      ][0], "")
    )
    : local.network_interfaces[0].ip != null ? split("/", local.network_interfaces[0].ip)[0] : ""
  )
}

output "network_interfaces" {
  description = "All configured network interfaces with IPs"
  value = [
    for nic in local.network_interfaces : {
      ip_mode      = nic.effective_ip_mode
      ip           = nic.ip
      bridge       = nic.bridge
      vlan_id      = nic.vlan_id
      vlan_devices = nic.vlan_devices
    }
  ]
}
