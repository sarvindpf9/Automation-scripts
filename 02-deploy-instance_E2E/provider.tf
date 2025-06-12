terraform {
  required_version = ">= 0.14.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0.0"
    }
  }
}

# public interface
provider "openstack" {
  insecure      = true
  endpoint_type = "public"
  user_name     = "${var.openstack_user_name}"
  tenant_name   = "${var.openstack_tenant_name}"
  password      = "${var.openstack_password}"
  auth_url      = "${var.openstack_auth_url}"
  region        = "${var.openstack_region}"
  domain_name   = "Default"
}

# Admin interface
provider "openstack" {
  alias         = "admin_interface"
  insecure      = true
  endpoint_type = "admin"
  user_name     = "${var.openstack_user_name}"
  tenant_name   = "${var.openstack_tenant_name}"
  password      = "${var.openstack_password}"
  auth_url      = "${var.openstack_auth_url}"
  region        = "${var.openstack_region}"
  domain_name   = "Default"
}
