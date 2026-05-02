# Custom private flavor — carries aggregate_instance_extra_specs to pin Nova scheduling
# to the target host aggregate. Admin credentials are required to create flavors.
resource "openstack_compute_flavor_v2" "custom_flavor" {
  name      = "${var.custom_name}-flavor"
  vcpus     = var.flavor_vcpus
  ram       = var.flavor_ram
  disk      = var.flavor_disk
  is_public = false

  extra_specs = {
    (local.agg_key) = local.agg_value
  }
}

# Grant the target tenant access to the private flavor
resource "openstack_compute_flavor_access_v2" "flavor_access" {
  flavor_id = openstack_compute_flavor_v2.custom_flavor.id
  tenant_id = data.openstack_identity_project_v3.tenant.id
}

resource "openstack_compute_instance_v2" "vm" {
  count           = var.instance_count
  name            = "${var.custom_name}-instance-${count.index}"
  flavor_id       = openstack_compute_flavor_v2.custom_flavor.id
  image_id        = local.image_id
  key_pair        = var.ssh_key_pair
  security_groups = [var.security_group]
  user_data       = file("${path.module}/cloud-init.yaml")

  # Boot-from-volume block — active only when boot_from_volume = true.
  # delete_on_termination controls whether the Cinder volume survives instance deletion.
  dynamic "block_device" {
    for_each = var.boot_from_volume ? [1] : []
    content {
      uuid                  = data.openstack_images_image_v2.image.id
      source_type           = "image"
      destination_type      = "volume"
      volume_size           = var.volume_size
      boot_index            = 0
      delete_on_termination = var.volume_delete_on_termination
    }
  }

  network {
    uuid = data.openstack_networking_network_v2.network.id
  }

  depends_on = [
    openstack_compute_flavor_access_v2.flavor_access,
  ]
}
