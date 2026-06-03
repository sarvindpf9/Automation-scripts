terraform {
  required_version = ">= 1.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.66"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

provider "proxmox" {
  endpoint = var.proxmox_url
  username = var.proxmox_api_username
  password = var.proxmox_api_password
  insecure = var.proxmox_insecure

  ssh {
    agent    = false
    username = var.proxmox_ssh_username
    password = var.proxmox_ssh_password
  }
}
