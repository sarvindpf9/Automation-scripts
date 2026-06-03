locals {
  template_vm_id = var.template_vm_id
  datastore_id   = var.datastore_id
  timestamp      = formatdate("YYYY-MM-DD hh:mm:ss ZZZ", timestamp())

  # Sanitize VM names for use in resource IDs
  vm_deployments = {
    for key, vm_config in var.vms :
    key => merge(vm_config, {
      sanitized_name = replace(vm_config.vm_name, "/[^a-zA-Z0-9-]/", "-")
    })
  }
}