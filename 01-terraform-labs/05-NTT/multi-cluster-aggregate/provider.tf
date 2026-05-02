terraform {
  required_version = ">= 0.14.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

# Public endpoint — standard resource operations
provider "openstack" {
  insecure      = true
  endpoint_type = "public"
  user_name     = var.openstack_user_name
  tenant_name   = var.openstack_tenant_name
  password      = var.openstack_password
  auth_url      = var.openstack_auth_url
  region        = var.openstack_region
  domain_name   = "Default"
}

# Admin endpoint — flavor creation and identity lookups require admin access
provider "openstack" {
  alias         = "admin_interface"
  insecure      = true
  endpoint_type = "admin"
  user_name     = var.openstack_user_name
  tenant_name   = var.openstack_tenant_name
  password      = var.openstack_password
  auth_url      = var.openstack_auth_url
  region        = var.openstack_region
  domain_name   = "Default"
}
