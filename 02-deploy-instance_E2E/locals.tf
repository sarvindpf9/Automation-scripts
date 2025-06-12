# Use the correct image_id based on condition
locals {
  selected_image_id = var.deploy_image ? openstack_images_image_v2.image[0].id : data.openstack_images_image_v2.existing_image[0].id
}