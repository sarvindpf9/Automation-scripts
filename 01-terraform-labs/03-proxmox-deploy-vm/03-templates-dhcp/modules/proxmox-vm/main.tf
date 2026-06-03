
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.66"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

locals {
  vm_name_slug = replace(var.vm_config.vm_name, "/[^a-zA-Z0-9-]/", "-")
  network_interfaces = [
    for nic in var.vm_config.network_interfaces : merge(nic, {
      effective_ip_mode = nic.ip_mode != null ? nic.ip_mode : nic.ip != null ? "static" : "none"
    })
  ]
  requires_guest_agent = anytrue([
    for nic in local.network_interfaces : nic.effective_ip_mode == "dhcp"
  ])
  primary_ip_file = "${path.module}/.terraform/generated/${local.vm_name_slug}-${var.vm_config.vm_id}-primary-ip.json"
}

# Pre-flight check: abort before the clone starts if the target VM ID already
# exists anywhere in the Proxmox cluster. Without this, Proxmox can create part
# of the clone and fail while writing
# the config, but Terraform times out and never records it in state — leaving
# an orphaned VM that blocks every subsequent apply with a "File exists" error.
resource "null_resource" "vm_id_precheck" {
  triggers = {
    vm_id     = var.vm_config.vm_id
    node_name = var.proxmox_node
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail

      ticket_resp=$(curl -sf -k -X POST \
        --data-urlencode "username=${var.proxmox_api_username}" \
        --data-urlencode "password=${var.proxmox_api_password}" \
        "${var.proxmox_url}/api2/json/access/ticket")

      ticket=$(printf '%s' "$${ticket_resp}" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["ticket"])')

      cluster_vms=$(curl -sf -k \
        -b "PVEAuthCookie=$${ticket}" \
        "${var.proxmox_url}/api2/json/cluster/resources?type=vm")

      existing_vm=$(printf '%s' "$${cluster_vms}" | python3 -c '
import json
import sys

target = int("${var.vm_config.vm_id}")
for item in json.load(sys.stdin)["data"]:
    if item.get("vmid") == target:
        node = item.get("node", "<unknown-node>")
        name = item.get("name", "<unknown-name>")
        print(f"{node}/{target} {name}")
        break
')

      if [ -n "$${existing_vm}" ]; then
        echo ""
        echo "ERROR: VM ID ${var.vm_config.vm_id} already exists in the Proxmox cluster: $${existing_vm}"
        echo ""
        echo "This is likely an orphan from a previous failed apply where the clone"
        echo "completed on Proxmox but Terraform timed out before writing state."
        echo ""
        echo "Resolution options:"
        echo "  A) If the VM booted correctly, import it into Terraform state:"
        echo "     terraform import 'module.proxmox_vms[\"<key>\"].proxmox_virtual_environment_vm.vm' ${var.proxmox_node}/${var.vm_config.vm_id}"
        echo ""
        echo "  B) If the VM is a partial/stale clone, destroy it and re-apply:"
        echo "     ssh root@<proxmox-node> 'qm stop ${var.vm_config.vm_id} --skiplock; qm destroy ${var.vm_config.vm_id} --purge'"
        echo ""
        exit 1
      fi
    EOT
  }
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
        - systemctl enable --now qemu-guest-agent || true
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
      %{~for idx, nic in local.network_interfaces}
        eth${idx}:
      %{~if nic.effective_ip_mode == "dhcp"}
          dhcp4: true
          dhcp6: false
          optional: true
      %{~else}
          dhcp4: false
      %{~if nic.effective_ip_mode == "none"}
          dhcp6: false
          optional: true
      %{~endif}
      %{~if nic.effective_ip_mode == "static"}
          addresses:
            - ${nic.ip}
      %{~endif}
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
      %{~if anytrue([for nic in local.network_interfaces : length(nic.vlan_devices) > 0])}
      vlans:
      %{~for idx, nic in local.network_interfaces}
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
  description = "Deployed via Terraform from Ubuntu 24 template (IP ${local.network_interfaces[0].effective_ip_mode == "dhcp" ? "DHCP" : local.network_interfaces[0].ip != null ? split("/", local.network_interfaces[0].ip)[0] : "N/A"})"
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
    for_each = local.network_interfaces
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
    enabled = true
    timeout = "15m"

    dynamic "wait_for_ip" {
      for_each = local.requires_guest_agent ? [1] : []

      content {
        ipv4 = true
      }
    }
  }

  # Start VM immediately after creation
  started = true

  # Boot configuration
  boot_order = ["scsi0"]

  # Static-only VMs keep IP waiting disabled. DHCP VMs require qemu-guest-agent
  # in the template so Terraform can learn the assigned IP.
  # 900s (15 min) matches the agent timeout above; 60s is too short for first-boot
  # cloud-init and leaves an orphaned VM config in Proxmox on timeout.
  timeout_start_vm = 900

  # Lifecycle management
  lifecycle {
    ignore_changes = [
      clone,
      initialization,
    ]
  }

  depends_on = [
    null_resource.vm_id_precheck,
    proxmox_virtual_environment_file.user_data,
    proxmox_virtual_environment_file.network_data,
  ]
}

resource "null_resource" "wait_for_primary_ip" {
  count = local.network_interfaces[0].effective_ip_mode == "dhcp" ? 1 : 0

  triggers = {
    vm_id                 = proxmox_virtual_environment_vm.vm.vm_id
    initial_delay_seconds = var.guest_agent_ip_initial_delay_seconds
    max_wait_seconds      = var.guest_agent_ip_max_wait_seconds
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]

    command = <<-EOT
      set -euo pipefail

      mkdir -p "$(dirname "${local.primary_ip_file}")"

      if [ "${var.guest_agent_ip_initial_delay_seconds}" -gt 0 ]; then
        sleep "${var.guest_agent_ip_initial_delay_seconds}"
      fi

      ticket_response=$(curl -sf -k -X POST \
        --data-urlencode "username=${var.proxmox_api_username}" \
        --data-urlencode "password=${var.proxmox_api_password}" \
        "${var.proxmox_url}/api2/json/access/ticket")

      ticket=$(printf '%s' "$${ticket_response}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["data"]["ticket"])')

      deadline=$((SECONDS + ${var.guest_agent_ip_max_wait_seconds}))
      while [ "$SECONDS" -lt "$deadline" ]; do
        agent_response=$(curl -sf -k \
          -b "PVEAuthCookie=$${ticket}" \
          "${var.proxmox_url}/api2/json/nodes/${var.proxmox_node}/qemu/${var.vm_config.vm_id}/agent/network-get-interfaces" || true)

        primary_ip=$(printf '%s' "$${agent_response}" | python3 -c '
import ipaddress
import json
import sys

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

interfaces = payload.get("data", {}).get("result", [])
for interface in interfaces:
    for address in interface.get("ip-addresses", []):
        if address.get("ip-address-type") != "ipv4":
            continue
        value = address.get("ip-address")
        if not value:
            continue
        ip = ipaddress.ip_address(value)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            continue
        print(value)
        sys.exit(0)
')

        if [ -n "$${primary_ip}" ]; then
          printf '{"primary_ip":"%s"}\n' "$${primary_ip}" > "${local.primary_ip_file}"
          exit 0
        fi

        sleep 10
      done

      echo "ERROR: timed out waiting for a non-loopback IPv4 address from QEMU guest agent for VM ${var.vm_config.vm_id}" >&2
      exit 1
    EOT
  }

  depends_on = [proxmox_virtual_environment_vm.vm]
}

data "local_file" "primary_ip" {
  count = local.network_interfaces[0].effective_ip_mode == "dhcp" ? 1 : 0

  filename   = local.primary_ip_file
  depends_on = [null_resource.wait_for_primary_ip]
}

# Detach cloud-init drive after first boot — cloud-init has already run by this point.
# Uses username/password API auth to avoid requiring a Proxmox API token.
resource "null_resource" "detach_cloudinit_drive" {
  triggers = {
    vm_id = proxmox_virtual_environment_vm.vm.vm_id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]

    command = <<-EOT
      set -euo pipefail

      ticket_response=$(curl -s -k -X POST \
        --data-urlencode "username=${var.proxmox_api_username}" \
        --data-urlencode "password=${var.proxmox_api_password}" \
        "${var.proxmox_url}/api2/json/access/ticket")

      ticket=$(printf '%s' "$${ticket_response}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["data"]["ticket"])')
      csrf_token=$(printf '%s' "$${ticket_response}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["data"]["CSRFPreventionToken"])')

      curl -s -k -X PUT \
        -b "PVEAuthCookie=$${ticket}" \
        -H "CSRFPreventionToken: $${csrf_token}" \
        "${var.proxmox_url}/api2/json/nodes/${var.proxmox_node}/qemu/${var.vm_config.vm_id}/config" \
        -d "delete=ide2"
    EOT
  }

  depends_on = [proxmox_virtual_environment_vm.vm]
}
