
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.66"
    }
  }
}

locals {
  vm_name_slug = replace(var.vm_config.vm_name, "/[^a-zA-Z0-9-]/", "-")
}

# Generate secure random password for VM (stored in Terraform state)
resource "random_password" "vm_password" {
  length      = 20
  special     = true
  min_special = 2
}

# Cloud-init user-data snippet uploaded to Proxmox local storage
resource "proxmox_virtual_environment_file" "user_data" {
  content_type = "snippets"
  datastore_id = var.snippet_datastore_id
  node_name    = var.proxmox_node

  source_raw {
    file_name = "${local.vm_name_slug}-user-data.yaml"
    data      = <<-EOF
      #cloud-config
      hostname: ${var.vm_config.vm_name}
      manage_etc_hosts: true
      users:
        - name: ubuntu
          shell: /bin/bash
          sudo: ALL=(ALL) NOPASSWD:ALL
          ssh_authorized_keys:
            - ${var.ssh_public_key}
      chpasswd:
        list: |
          ubuntu:password
        expire: false
      package_update: false
      write_files:
        - path: /usr/local/bin/apply-netplan.sh
          permissions: '0755'
          content: |
            #!/bin/bash
            # Discover virtio_net interfaces sorted by virtio device number (virtio0, virtio1...).
            # Sorting by device number — not interface name — guarantees the array index matches
            # the Proxmox NIC slot order and therefore the cloud-init eth0/eth1 placeholders.
            IFACES=()
            for v in $(ls /sys/bus/virtio/drivers/virtio_net/ 2>/dev/null \
                         | grep '^virtio[0-9]' | sort -V); do
              iface=$(ls /sys/bus/virtio/drivers/virtio_net/$${v}/net/ 2>/dev/null | head -1)
              [ -n "$${iface}" ] && IFACES+=("$${iface}")
            done

            NETPLAN=/etc/netplan/50-cloud-init.yaml

            # Replace ethN placeholders with real interface names.
            # Single ERE pass: word-boundary via surrounding non-alnum chars covers
            # all occurrences (ethN:, ethN.VLAN:, link: ethN) without ordering concerns.
            for i in "$${!IFACES[@]}"; do
              REAL_IF="$${IFACES[$i]}"
              sed -i -E "s/(^|[^a-zA-Z0-9_])eth$${i}([^a-zA-Z0-9_]|$)/\1$${REAL_IF}\2/g" "$NETPLAN"
            done

            chmod 600 "$NETPLAN"
            netplan apply
      runcmd:
        - /usr/local/bin/apply-netplan.sh
    EOF
  }
}

# Cloud-init network-config snippet uploaded to Proxmox local storage
resource "proxmox_virtual_environment_file" "network_data" {
  content_type = "snippets"
  datastore_id = var.snippet_datastore_id
  node_name    = var.proxmox_node

  source_raw {
    file_name = "${local.vm_name_slug}-network-data.yaml"
    data      = <<-EOF
      version: 2
      ethernets:
      %{~for idx, nic in var.vm_config.network_interfaces}
        eth${idx}:
          dhcp4: false
      %{~if nic.ip == null}
          dhcp6: false
          optional: true
      %{~endif}
      %{~if nic.ip != null}
          addresses:
            - ${nic.ip}
      %{~endif}
      %{~if nic.gw != null}
          routes:
            - to: default
              via: ${nic.gw}
      %{~endif}
      %{~if nic.dns != null}
          nameservers:
            addresses: ${jsonencode(nic.dns)}
      %{~endif}
      %{~endfor}
      %{~if anytrue([for nic in var.vm_config.network_interfaces : length(nic.vlan_devices) > 0])}
      vlans:
      %{~for idx, nic in var.vm_config.network_interfaces}
      %{~for vdev in nic.vlan_devices}
        eth${idx}.${vdev.id}:
          id: ${vdev.id}
          link: eth${idx}
          addresses:
            - ${vdev.ip}
      %{~if vdev.gw != null}
          routes:
            - to: default
              via: ${vdev.gw}
      %{~endif}
      %{~endfor}
      %{~endfor}
      %{~endif}
    EOF
  }
}

# Main VM resource - Cloned from template
resource "proxmox_virtual_environment_vm" "vm" {
  vm_id       = var.vm_config.vm_id
  name        = var.vm_config.vm_name
  description = "Deployed via Terraform from Ubuntu 24 template (IP ${var.vm_config.network_interfaces[0].ip != null ? split("/", var.vm_config.network_interfaces[0].ip)[0] : "N/A"})"
  node_name   = var.proxmox_node

  # Clone from template
  clone {
    vm_id        = var.template_vm_id
    node_name    = var.proxmox_node
    full         = true
    datastore_id = var.datastore_id
  }

  # CPU configuration
  cpu {
    cores   = var.vm_config.cores
    sockets = var.vm_config.sockets
    type    = "host"
  }

  # Memory configuration
  memory {
    dedicated = var.vm_config.memory_mb
  }

  # Network interfaces — one proxmox NIC per entry in network_interfaces list
  # vlan_id = null means untagged port (no VLAN tag applied by the provider)
  dynamic "network_device" {
    for_each = var.vm_config.network_interfaces
    content {
      bridge  = network_device.value.bridge
      vlan_id = network_device.value.vlan_id
    }
  }

  # Explicitly place the cloned disk on the target datastore, avoiding any
  # stale storage reference (e.g. local-lvm) that may exist on the template VM.
  disk {
    size         = var.vm_config.disk_size_gb
    datastore_id = var.datastore_id
    interface    = "scsi0"
    aio          = "native"
    backup       = false
  }

  # Cloud-Init via snippets
  initialization {
    datastore_id         = var.datastore_id
    user_data_file_id    = proxmox_virtual_environment_file.user_data.id
    network_data_file_id = proxmox_virtual_environment_file.network_data.id
  }

  # QEMU Guest Agent
  agent {
    enabled = false
  }

  # Start VM immediately after creation
  started = true

  # Boot configuration
  boot_order = ["scsi0"]

  # Template has no QEMU guest agent — skip waiting for agent/IP readiness
  timeout_start_vm = 60

  # Lifecycle management
  lifecycle {
    ignore_changes = [
      clone,
      initialization,
    ]
  }

  depends_on = [
    proxmox_virtual_environment_file.user_data,
    proxmox_virtual_environment_file.network_data,
  ]
}

# Detach cloud-init drive after first boot — cloud-init has already run by this point.
# Uses the Proxmox API via curl; requires no SSH access to the VM itself.
resource "null_resource" "detach_cloudinit_drive" {
  triggers = {
    vm_id = proxmox_virtual_environment_vm.vm.vm_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      curl -s -k -X PUT \
        -H "Authorization: PVEAPIToken=${var.proxmox_api_token}" \
        "${var.proxmox_url}/api2/json/nodes/${var.proxmox_node}/qemu/${var.vm_config.vm_id}/config" \
        -d "delete=ide2"
    EOT
  }

  depends_on = [proxmox_virtual_environment_vm.vm]
}
