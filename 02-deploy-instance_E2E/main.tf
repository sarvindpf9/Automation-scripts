resource "openstack_networking_network_v2" "network" {
  name = "${var.custom_name}-net"
}

# Create subnet
resource "openstack_networking_subnet_v2" "subnet" {
  name       = "${var.custom_name}-subnet"
  network_id = openstack_networking_network_v2.network.id
  cidr       = "172.16.0.0/24"
  ip_version = 4
}

# Upload image from file if deploy_image is true
resource "openstack_images_image_v2" "image" {
  count            = var.deploy_image ? 1 : 0
  provider         = openstack.admin_interface
  name             = "${var.glance_image_name}"
  local_file_path  = "${path.module}/${var.glance_image_name}"
  container_format = "bare"
  disk_format      = "qcow2"
}


# Create volume (if deploy_volume is true)
resource "openstack_blockstorage_volume_v3" "volume" {
  count       = var.deploy_volume ? 1 : 0
  name        = "${var.custom_name}-vol"
  size        = 2
  volume_type = "nfs-cinder"
}

# Launch instance
resource "openstack_compute_instance_v2" "vm" {
  name        = "${var.custom_name}-instance"
  image_id    = local.selected_image_id
  flavor_name = var.flavor_name
  user_data   = data.template_file.cloud_init.rendered

  network {
    name = openstack_networking_network_v2.network.name
  }

  depends_on = [
    openstack_networking_subnet_v2.subnet
  ]
}

# Attach volume to instance (if volume created)
resource "openstack_compute_volume_attach_v2" "attach" {
  count       = var.deploy_volume ? 1 : 0
  instance_id = openstack_compute_instance_v2.vm.id
  volume_id   = openstack_blockstorage_volume_v3.volume[0].id
}
