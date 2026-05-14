output "instance_names" {
  value       = openstack_compute_instance_v2.vm[*].name
  description = "Names of all deployed instances"
}

output "instance_ips" {
  value       = openstack_compute_instance_v2.vm[*].access_ip_v4
  description = "IP addresses assigned to all instances"
}

output "instance_details" {
  value = {
    for vm in openstack_compute_instance_v2.vm :
    vm.name => {
      id = vm.id
      ip = vm.access_ip_v4
    }
  }
  description = "Map of instance name to id and IP for all deployed instances"
}

output "image_name" {
  value       = var.deploy_image ? openstack_images_image_v2.image[0].name : data.openstack_images_image_v2.existing_image[0].name
  description = "Glance image used for instance creation"
}

output "flavor_details" {
  value = var.create_flavor ? {
    name  = openstack_compute_flavor_v2.flavor[0].name
    vcpus = openstack_compute_flavor_v2.flavor[0].vcpus
    ram   = openstack_compute_flavor_v2.flavor[0].ram
    disk  = openstack_compute_flavor_v2.flavor[0].disk
    } : {
    name  = data.openstack_compute_flavor_v2.flavor[0].name
    vcpus = data.openstack_compute_flavor_v2.flavor[0].vcpus
    ram   = data.openstack_compute_flavor_v2.flavor[0].ram
    disk  = data.openstack_compute_flavor_v2.flavor[0].disk
  }
  description = "Flavor name, vCPUs, RAM (MB), and root disk (GB) for all instances"
}

output "vm_network_name" {
  value       = var.vm_network_name
  description = "Network attached to instances"
}

output "created_networks" {
  value = {
    for name, net in openstack_networking_network_v2.networks :
    name => {
      network_id = net.id
      subnet_id  = openstack_networking_subnet_v2.subnets[name].id
      cidr       = openstack_networking_subnet_v2.subnets[name].cidr
    }
  }
  description = "Networks and subnets created by this module (empty map when networks_to_create = [])"
}

output "data_volume_names" {
  value       = var.deploy_volume ? openstack_blockstorage_volume_v3.volume[*].name : []
  description = "Cinder data volume names attached to instances (empty list when deploy_volume = false)"
}

output "boot_mode" {
  value       = var.boot_from_volume ? "boot-from-volume (${var.boot_volume_size} GB, delete_on_termination=${var.boot_volume_delete_on_termination})" : "ephemeral"
  description = "Boot mode used for all instances"
}
