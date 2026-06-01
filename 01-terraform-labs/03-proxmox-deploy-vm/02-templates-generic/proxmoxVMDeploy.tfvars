proxmox_url          = "https://192.168.1.82:8006"
proxmox_api_username = "root@pam"
proxmox_api_password = "Qwerty#1234"
proxmox_insecure     = true
proxmox_ssh_username = "root"
proxmox_ssh_password = "Qwerty#1234"
proxmox_node         = "homelab-pve"
template_vm_id       = 100
datastore_id         = "local-1TB"
snippet_datastore_id = "local"
ssh_public_key_path  = "~/.ssh/homelab-key.pub"
vms = {
  "vm1" = {
    vm_name   = "u24-test-server"
    vm_id     = 1000
    memory_mb = 4096
    cores     = 4
    sockets   = 1
    network_interfaces = [
      # NIC 0 — VLAN 500 tagged at bridge level, default route to external network
      {
        bridge       = "vyosvlanbr"
        vlan_id      = 500
        ip           = "172.17.0.111/20"
        gw           = "172.17.0.1"
        dns          = ["8.8.8.8", "8.8.4.4"]
        vlan_devices = []
      },
      # NIC 1 — untagged bridge port, no IP on the interface itself.
      # All traffic is carried by VLAN sub-interfaces defined below.
      {
        bridge = "vmbr0"
        # vlan_id omitted = no bridge-level VLAN tag (trunk/access as-is)
        # ip omitted      = no address on eth1 itself; sub-interfaces carry the IPs
        vlan_devices = [
          {
            id = 300
            ip = "192.168.30.10/24"
            gw = "192.168.30.1" # optional per-VLAN gateway
          },
          {
            id = 400
            ip = "192.168.40.10/24"
            # gw omitted — no gateway on this VLAN
          }
        ]
      }
    ]
  }
}
