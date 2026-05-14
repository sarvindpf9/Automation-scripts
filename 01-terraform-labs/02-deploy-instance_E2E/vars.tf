variable "openstack_user_name" {}
variable "openstack_tenant_name" {}
variable "openstack_region" {}
variable "openstack_password" {}
variable "openstack_auth_url" {}

variable "vm_name" {
  description = "Name suffix for instances; each is named demo-<vm_name>-<index>"
  type        = string
  default     = "node"
}

variable "vm_count" {
  description = "Number of identical instances to deploy"
  type        = number
  default     = 1
}

# --- Flavor ---

variable "flavor_name" {
  description = "Flavor name — used for both creation (create_flavor = true) and direct lookup (create_flavor = false)"
  type        = string
  default     = "m1.tiny"
}

variable "create_flavor" {
  description = "true = create a new flavor with the settings below; false = use an existing flavor by flavor_name"
  type        = bool
  default     = false
}

variable "flavor_vcpus" {
  description = "vCPU count for the new flavor (create_flavor = true)"
  type        = number
  default     = 1
}

variable "flavor_ram_mb" {
  description = "RAM in MB for the new flavor (create_flavor = true)"
  type        = number
  default     = 512
}

variable "flavor_disk_gb" {
  description = "Root disk in GB for the new flavor (create_flavor = true)"
  type        = number
  default     = 1
}

# --- Network ---

variable "networks_to_create" {
  description = "Networks and subnets to create. Each entry creates one Neutron network + subnet. Leave empty to use only existing networks."
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}

variable "vm_network_name" {
  description = "Network to attach instances to. Must match one of networks_to_create[*].name or an existing network accessible to this project."
  type        = string
  default     = "demo-net"
}

# --- Image ---

variable "image_name" {
  description = "Glance image name to look up when deploy_image = false"
  type        = string
  default     = "cirros-0.6.3"
}

variable "deploy_image" {
  description = "true = upload a local image file to Glance; false = look up existing image by image_name"
  type        = bool
  default     = false
}

variable "glance_image_name" {
  description = "Local image filename to upload when deploy_image = true (file must exist in the module directory)"
  type        = string
  default     = "cirros-0.6.3-x86_64-disk.img"
}

# --- Boot mode ---

variable "boot_from_volume" {
  description = "true = boot from a Cinder volume; false = ephemeral disk"
  type        = bool
  default     = false
}

variable "boot_volume_size" {
  description = "Boot volume size in GB (boot_from_volume = true only)"
  type        = number
  default     = 20
}

variable "boot_volume_delete_on_termination" {
  description = "Delete the boot volume when the instance is destroyed"
  type        = bool
  default     = true
}

# --- Data volume (separate from boot) ---

variable "deploy_volume" {
  description = "Attach a separate Cinder data volume to each instance"
  type        = bool
  default     = false
}

variable "data_volume_size" {
  description = "Data volume size in GB"
  type        = number
  default     = 10
}

variable "volume_type" {
  description = "Cinder volume type for data volumes"
  type        = string
  default     = "nfs-cinder"
}

# --- Cloud-init ---

variable "cloud_init_config" {
  description = "Inline cloud-init user-data. Leave empty to use cloud-init.yaml from this module directory."
  type        = string
  default     = ""
}

# --- Security / access ---

variable "security_group" {
  description = "Security group name to apply to instances"
  type        = string
  default     = "default"
}

variable "ssh_key_pair" {
  description = "Key pair name to inject; leave empty to skip"
  type        = string
  default     = ""
}
