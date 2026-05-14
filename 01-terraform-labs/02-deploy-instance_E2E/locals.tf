locals {
  # True when vm_network_name is one of the networks being created by this module
  network_is_managed = contains([for n in var.networks_to_create : n.name], var.vm_network_name)

  selected_image_id = var.deploy_image ? openstack_images_image_v2.image[0].id : data.openstack_images_image_v2.existing_image[0].id

  # When create_flavor = true the resource name is authoritative; otherwise pass the variable through
  selected_flavor_name = var.create_flavor ? openstack_compute_flavor_v2.flavor[0].name : var.flavor_name

  # Prefer inline variable; fall back to the cloud-init.yaml file in this module
  cloud_init_data = var.cloud_init_config != "" ? var.cloud_init_config : file("${path.module}/cloud-init.yaml")
}
