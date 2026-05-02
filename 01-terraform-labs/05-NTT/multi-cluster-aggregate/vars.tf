# --- Provider credentials (required, no defaults) ---
variable "openstack_user_name"   {}
variable "openstack_tenant_name" {}
variable "openstack_password"    {}
variable "openstack_auth_url"    {}
variable "openstack_region"      {}

# --- Naming ---
variable "custom_name" {
  description = "Naming prefix applied to all created resources."
  default     = "ntt-agg"
}

# --- Network ---
variable "network_name" {
  description = "Name of the existing OpenStack network to attach the instance to."
}

# --- Image ---
variable "glance_image_name" {
  description = "Name of the existing Glance image to boot from."
}

# --- Custom flavor dimensions ---
variable "flavor_vcpus" {
  description = "vCPU count for the custom flavor."
  type        = number
  default     = 2
}

variable "flavor_ram" {
  description = "RAM in MB for the custom flavor."
  type        = number
  default     = 4096
}

variable "flavor_disk" {
  description = "Root disk size in GB. Set to 0 when boot_from_volume = true."
  type        = number
  default     = 0
}

# --- Aggregate affinity ---
variable "aggregate_instance_extra_spec" {
  description = "Full aggregate extra spec in the form aggregate_instance_extra_specs:KEY=VALUE (e.g. 'aggregate_instance_extra_specs:workload=RHEL'). Set directly as a flavor extra spec key."
}

# --- Boot from volume ---
variable "boot_from_volume" {
  description = "If true, the instance boots from a Cinder volume created from the Glance image."
  type        = bool
  default     = false
}

variable "volume_size" {
  description = "Size of the boot volume in GB. Used only when boot_from_volume = true."
  type        = number
  default     = 50
}

variable "volume_delete_on_termination" {
  description = "When true the boot volume is deleted on instance termination. Used only when boot_from_volume = true."
  type        = bool
  default     = true
}

# --- Access ---
variable "ssh_key_pair" {
  description = "Name of the Nova keypair to inject into the instance."
  default     = "<SSH_KEYPAIR_NAME>"
}

variable "security_group" {
  description = "Security group name to apply to the instance."
  default     = "default"
}

# --- Scale ---
variable "instance_count" {
  description = "Number of instances to deploy."
  type        = number
  default     = 1
}
