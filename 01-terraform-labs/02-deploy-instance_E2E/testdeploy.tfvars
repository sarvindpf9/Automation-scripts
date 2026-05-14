# OpenStack credentials
openstack_user_name   = "sa@platform9.com"
openstack_tenant_name = "service"
openstack_password    = "Platform9!"
openstack_auth_url    = "https://sa-demo-region2.app.qa-pcd.platform9.com/keystone/v3"
openstack_region      = "region2"

# Instance
vm_name  = "test"    # instances will be named demo-test-1, demo-test-2, ...
vm_count = 1

# Flavor — option A: use an existing flavor
create_flavor = false
flavor_name   = "s1.tiny"

# Flavor — option B: create a new flavor (requires admin endpoint access; comment out option A)
# create_flavor  = true
# flavor_name    = "custom.2c4g"
# flavor_vcpus   = 2
# flavor_ram_mb  = 4096
# flavor_disk_gb = 20

# Network — option A: use an existing network
vm_network_name    = "demo-net"
networks_to_create = []

# Network — option B: create one or more networks and attach VMs to one of them
# vm_network_name = "lab-net-1"
# networks_to_create = [
#   { name = "lab-net-1", cidr = "192.168.10.0/24" },
#   { name = "lab-net-2", cidr = "192.168.20.0/24" },
# ]

# Image — option A: use an existing Glance image
image_name   = "cirros-0.6.3"
deploy_image = false

# Image — option B: upload a local image file (file must exist in this directory)
# deploy_image      = true
# glance_image_name = "cirros-0.6.3-x86_64-disk.img"

# Boot mode — false = ephemeral disk, true = boot from Cinder volume
boot_from_volume = false
# boot_volume_size                  = 20
# boot_volume_delete_on_termination = true    # set false to retain volume on destroy

# Data volume (attached separately, independent of boot mode)
deploy_volume = false
# data_volume_size = 10
# volume_type      = "nfs-cinder"

# Cloud-init — leave empty to use cloud-init.yaml; or supply inline:
# cloud_init_config = <<-EOF
#   #cloud-config
#   packages:
#     - curl
#     - jq
# EOF

# Access
security_group = "default"
# ssh_key_pair = "<KEY_PAIR_NAME>"
