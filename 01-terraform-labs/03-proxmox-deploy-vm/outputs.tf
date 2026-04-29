output "vm_ips" {
  description = "Deployed VM primary IP addresses"
  value = {
    for key, vm in module.proxmox_vms :
    vm.vm_name => vm.primary_ip
  }
}

output "vm_details" {
  description = "Complete VM deployment details"
  value = {
    for key, vm in module.proxmox_vms :
    vm.vm_name => {
      vm_id              = vm.vm_id
      primary_ip         = vm.primary_ip
      network_interfaces = vm.network_interfaces
    }
  }
}

resource "local_file" "ansible_inventory" {
  filename = "${path.module}/inventory.yml"

  content = templatefile("${path.module}/templates/host_inventory.tftpl", {
    vms = {
      for key, vm in module.proxmox_vms :
      vm.vm_name => {
        primary_ip = vm.primary_ip
      }
    }

    timestamp = local.timestamp
  })

  depends_on = [module.proxmox_vms]
}

output "ansible_inventory_path" {
  description = "Path to generated Ansible inventory"
  value       = local_file.ansible_inventory.filename
}

output "terraform_outputs_summary" {
  description = "Summary of all outputs"
  value = {
    total_vms_deployed  = length(module.proxmox_vms)
    vm_names            = [for vm in module.proxmox_vms : vm.vm_name]
    ansible_inventory   = local_file.ansible_inventory.filename
    primary_ips = { for key, vm in module.proxmox_vms : vm.vm_name => vm.primary_ip }
    deployment_complete = "true"
  }
}
