openstack_user_name   = "<OS_USERNAME>"
openstack_tenant_name = "<OS_TENANT>"
openstack_password    = "<OS_PASSWORD>"
openstack_auth_url    = "<KEYSTONE_ENDPOINT>/v3"
openstack_region      = "<REGION_NAME>"

network_name      = "<EXISTING_NETWORK_NAME>"
glance_image_name = "<GLANCE_IMAGE_NAME>"

# Custom flavor dimensions
flavor_vcpus = 2
flavor_ram   = 4096
flavor_disk  = 0        # keep 0 when boot_from_volume = true

# Host aggregate affinity — format: aggregate_instance_extra_specs:KEY=VALUE
# The scheduler places instances only on hosts in aggregates whose metadata matches.
# Example: aggregate_instance_extra_spec = "aggregate_instance_extra_specs:workload=RHEL"
aggregate_instance_extra_spec = "aggregate_instance_extra_specs:<KEY>=<VALUE>"

# Boot from volume
boot_from_volume             = false
volume_size                  = 50
volume_delete_on_termination = true   # set false to retain volume on instance delete

ssh_key_pair   = "<SSH_KEYPAIR_NAME>"
security_group = "default"
instance_count = 1
