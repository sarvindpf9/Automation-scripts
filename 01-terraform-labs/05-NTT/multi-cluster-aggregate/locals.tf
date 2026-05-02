locals {
  # When booting from volume the image_id at instance level must be null;
  # Nova derives the boot image from the block_device stanza instead.
  image_id = var.boot_from_volume ? null : data.openstack_images_image_v2.image.id

  timestamp = formatdate("YYYY-MM-DD hh:mm:ss ZZZ", timestamp())

  # Split "aggregate_instance_extra_specs:KEY=VALUE" on "=" to separate the full spec key from its value.
  _agg_parts = split("=", var.aggregate_instance_extra_spec)
  agg_key    = local._agg_parts[0]
  agg_value  = join("=", slice(local._agg_parts, 1, length(local._agg_parts)))
}
