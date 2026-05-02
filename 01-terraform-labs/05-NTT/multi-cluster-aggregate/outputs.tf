output "vm_ip_map" {
  description = "Map of deployed VM name to its assigned IP address."
  value = {
    for vm in openstack_compute_instance_v2.vm :
    vm.name => vm.access_ip_v4
  }
}

output "flavor_name" {
  description = "Name of the custom flavor created for this deployment."
  value       = openstack_compute_flavor_v2.custom_flavor.name
}

output "flavor_extra_specs" {
  description = "Extra specs on the custom flavor (encodes the aggregate affinity constraint)."
  value       = openstack_compute_flavor_v2.custom_flavor.extra_specs
}

output "image_name" {
  description = "Glance image used for instance creation."
  value       = data.openstack_images_image_v2.image.name
}

output "network_name" {
  description = "Network the instances are attached to."
  value       = data.openstack_networking_network_v2.network.name
}

output "boot_volume_policy" {
  description = "Effective boot volume retention policy."
  value       = var.boot_from_volume ? (var.volume_delete_on_termination ? "delete-on-termination" : "retain") : "ephemeral-disk"
}

# Written to module directory on every apply — add inventory.yml to .gitignore
resource "local_file" "ansible_inventory" {
  filename = "${path.module}/inventory.yml"
  content = templatefile("${path.module}/templates/host_inventory.tftpl", {
    vms = {
      for vm in openstack_compute_instance_v2.vm :
      vm.name => { primary_ip = vm.access_ip_v4 }
    }
    timestamp = local.timestamp
  })
  depends_on = [openstack_compute_instance_v2.vm]
}

output "ansible_inventory_path" {
  description = "Path to the generated Ansible inventory file."
  value       = local_file.ansible_inventory.filename
}

output "terraform_outputs_summary" {
  description = "Consolidated deployment summary."
  value = {
    total_vms_deployed  = length(openstack_compute_instance_v2.vm)
    vm_names            = openstack_compute_instance_v2.vm[*].name
    vm_ip_map           = { for vm in openstack_compute_instance_v2.vm : vm.name => vm.access_ip_v4 }
    ansible_inventory   = local_file.ansible_inventory.filename
    deployment_complete = "true"
  }
}
