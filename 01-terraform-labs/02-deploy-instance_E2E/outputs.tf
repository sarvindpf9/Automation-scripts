# Print the name of the image used (uploaded or looked up)
output "image_name" {
  value = var.deploy_image ? openstack_images_image_v2.image[0].name : data.openstack_images_image_v2.existing_image[0].name
  description = "Name of the Glance image used for instance creation"
}

# Print the IP address of the instance
output "instance_ip" {
  value       = openstack_compute_instance_v2.vm.access_ip_v4
  description = "IP address assigned to the instance"
}

# Print the name of the network created
output "network_name" {
  value       = openstack_networking_network_v2.network.name
  description = "Name of the created network"
}

# Print the name of the subnet created
output "subnet_name" {
  value       = openstack_networking_subnet_v2.subnet.name
  description = "Name of the created subnet"
}

# Print the name of the block storage volume
output "volume_name" {
  value       = var.deploy_volume ? openstack_blockstorage_volume_v3.volume[0].name : "No volume deployed"
  description = "Name of the Cinder volume attached to the instance"
}