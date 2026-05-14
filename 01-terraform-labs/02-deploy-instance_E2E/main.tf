# Create one Neutron network per entry in networks_to_create
resource "openstack_networking_network_v2" "networks" {
  for_each = { for n in var.networks_to_create : n.name => n }
  name     = each.value.name
}

resource "openstack_networking_subnet_v2" "subnets" {
  for_each   = { for n in var.networks_to_create : n.name => n }
  name       = "${each.value.name}-subnet"
  network_id = openstack_networking_network_v2.networks[each.key].id
  cidr       = each.value.cidr
  ip_version = 4
}

# Upload image from local file when deploy_image = true
resource "openstack_images_image_v2" "image" {
  count            = var.deploy_image ? 1 : 0
  provider         = openstack.admin_interface
  name             = var.glance_image_name
  local_file_path  = "${path.module}/${var.glance_image_name}"
  container_format = "bare"
  disk_format      = "qcow2"
}

# Create flavor when create_flavor = true; requires admin endpoint access
resource "openstack_compute_flavor_v2" "flavor" {
  count    = var.create_flavor ? 1 : 0
  provider = openstack.admin_interface
  name     = var.flavor_name
  vcpus    = var.flavor_vcpus
  ram      = var.flavor_ram_mb
  disk     = var.flavor_disk_gb
}

# One data volume per instance when deploy_volume = true
resource "openstack_blockstorage_volume_v3" "volume" {
  count       = var.deploy_volume ? var.vm_count : 0
  name        = "demo-${var.vm_name}-${count.index + 1}-vol"
  size        = var.data_volume_size
  volume_type = var.volume_type
}

# Launch instances
resource "openstack_compute_instance_v2" "vm" {
  count       = var.vm_count
  name        = "demo-${var.vm_name}-${count.index + 1}"
  flavor_name = local.selected_flavor_name
  user_data   = local.cloud_init_data

  # image_id is only set for ephemeral boot; boot-from-volume drives boot via block_device
  image_id = var.boot_from_volume ? null : local.selected_image_id

  key_pair        = var.ssh_key_pair != "" ? var.ssh_key_pair : null
  security_groups = [var.security_group]

  dynamic "block_device" {
    for_each = var.boot_from_volume ? [1] : []
    content {
      uuid                  = local.selected_image_id
      source_type           = "image"
      destination_type      = "volume"
      volume_size           = var.boot_volume_size
      boot_index            = 0
      delete_on_termination = var.boot_volume_delete_on_termination
    }
  }

  network {
    name = var.vm_network_name
  }

  # Ensure managed subnets exist before instances are created
  depends_on = [openstack_networking_subnet_v2.subnets]
}

# Attach one data volume per instance
resource "openstack_compute_volume_attach_v2" "attach" {
  count       = var.deploy_volume ? var.vm_count : 0
  instance_id = openstack_compute_instance_v2.vm[count.index].id
  volume_id   = openstack_blockstorage_volume_v3.volume[count.index].id
}
