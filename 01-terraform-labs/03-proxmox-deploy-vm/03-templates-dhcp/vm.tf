module "proxmox_vms" {
  for_each = local.vm_deployments

  source = "./modules/proxmox-vm"

  proxmox_node         = var.proxmox_node
  proxmox_url          = var.proxmox_url
  proxmox_api_username = var.proxmox_api_username
  proxmox_api_password = var.proxmox_api_password
  template_vm_id       = local.template_vm_id
  datastore_id         = local.datastore_id
  snippet_datastore_id = var.snippet_datastore_id
  vm_config            = each.value
  ssh_public_key       = file(var.ssh_public_key_path)

  guest_agent_ip_initial_delay_seconds = var.guest_agent_ip_initial_delay_seconds
  guest_agent_ip_max_wait_seconds      = var.guest_agent_ip_max_wait_seconds
}
