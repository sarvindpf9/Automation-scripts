data "openstack_images_image_v2" "image" {
  name        = var.glance_image_name
  most_recent = true
}

data "openstack_networking_network_v2" "network" {
  name = var.network_name
}

data "openstack_identity_project_v3" "tenant" {
  name = var.openstack_tenant_name
}
