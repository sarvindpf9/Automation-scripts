resource "openstack_networking_network_v2" "networks" {
  count = var.resourcecount["net"]
  name  = "${var.custom_name}-net-${count.index}"
}

resource "openstack_networking_subnet_v2" "subnets" {
  count       = var.resourcecount["net"]
  name        = "${var.custom_name}-subnet-${count.index}"
  network_id  = openstack_networking_network_v2.networks[count.index].id
  cidr        = "172.16.${count.index}.0/24"
  ip_version  = 4
}

resource "openstack_blockstorage_volume_v3" "volumes" {
  count       = var.deploy_volume ? var.resourcecount["vol"] : 0
  name        = "${var.custom_name}-vol-${count.index}"
  size        = 3
  volume_type = "lvm"
}

resource "openstack_images_image_v2" "images" {
  count             = var.deploy_image ? var.resourcecount["imgs"] : 0
  provider          = openstack.admin_interface
  name              = "${var.custom_name}-cirros063-${count.index}"
  local_file_path   = "${path.module}/${var.glance_image_name}"
  container_format  = "bare"
  disk_format       = "qcow2"
}

resource "openstack_compute_instance_v2" "vms" {
  count        = var.resourcecount["inst"]
  name         = "${var.custom_name}-instance-${count.index}"
  image_id     = "${data.openstack_images_image_v2.image_name.id}"
  flavor_name  = "${var.flavor_name}"
  user_data    = data.template_file.cloud_init.rendered

  network {
    name = "${var.custom_name}-net-${count.index}"
  }
  depends_on = [
    	openstack_networking_subnet_v2.subnets,
	openstack_networking_network_v2.networks
  ]
}

