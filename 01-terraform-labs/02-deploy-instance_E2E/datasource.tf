data "openstack_images_image_v2" "existing_image" {
  count = var.deploy_image ? 0 : 1
  name  = var.image_name
}

# Look up existing network only when vm_network_name is not managed by this module
data "openstack_networking_network_v2" "existing_network" {
  count = local.network_is_managed ? 0 : 1
  name  = var.vm_network_name
}

# Look up flavor details for output when using an existing flavor
data "openstack_compute_flavor_v2" "flavor" {
  count = var.create_flavor ? 0 : 1
  name  = var.flavor_name
}
