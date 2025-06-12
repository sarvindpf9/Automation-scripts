data "template_file" "cloud_init" {
  template = file("${path.module}/cloud-init.yaml")
}

data "openstack_compute_flavor_v2" "flavor_name" {
  name = var.flavor_name 
}

data "openstack_images_image_v2" "existing_image" {
  count = var.deploy_image ? 0 : 1
  name  = var.image_name
}
