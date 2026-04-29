module "proxmox_vms" {
  for_each = local.vm_deployments

  source = "./modules/proxmox-vm"

  proxmox_node         = var.proxmox_node
  proxmox_url          = var.proxmox_url
  proxmox_api_token    = var.proxmox_api_token
  template_vm_id       = local.template_vm_id
  datastore_id         = local.datastore_id
  snippet_datastore_id = var.snippet_datastore_id
  vm_config            = each.value
  ssh_public_key       = file(var.ssh_public_key_path)
}