variable "openstack_user_name" {}
variable "openstack_tenant_name" {}
variable "openstack_region" {}
variable "openstack_password" {}
variable "openstack_auth_url" {}
variable "image" {
  default = "cirros"
}

variable "flavor" {
  default = "m1.tiny"
}

variable "ssh_key_pair" {
  default = "mykey"
}

variable "custom_name" {
  default = "demo_run"
}

variable "image_name" {
  default = "cirros-0.6.3new"
}

variable "flavor_name" {
  default = "m1.tiny"
}

variable "ssh_user_name" {
  default = "ubuntu"
}

variable "security_group" {
   default = "default"
}

variable "network" {
   default  = "demo-net"
}

variable "glance_image_name" {
   default  = "cirros-0.6.3"
}

variable "deploy_image" {
  type    = bool
  default = false
}

variable "deploy_volume" {
  type    = bool
  default = false
}

variable "cidr" {
  type    = string
  default = "192.168.200.0/24"
}