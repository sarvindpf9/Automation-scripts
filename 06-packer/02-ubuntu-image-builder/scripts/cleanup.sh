#!/usr/bin/env bash
set -euo pipefail

# ── Package cache ──────────────────────────────────────────────────────────────
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/*

# ── Packer build sudoers rule — remove before image is sealed ─────────────────
rm -f /etc/sudoers.d/packer

# ── SSH host keys — removed so each deployed instance regenerates its own ─────
rm -f /etc/ssh/ssh_host_*

# ── Machine identity ───────────────────────────────────────────────────────────
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -sf /etc/machine-id /var/lib/dbus/machine-id

# ── Cloud-init state — reset so it reruns on first boot of deployed instance ──
if command -v cloud-init &>/dev/null; then
  cloud-init clean --logs
fi

# ── Logs and temporary files ───────────────────────────────────────────────────
find /var/log -type f -exec truncate -s 0 {} \;
rm -rf /tmp/* /var/tmp/*
history -c 2>/dev/null || true
cat /dev/null > /root/.bash_history

# ── Zero free space — improves qcow2 compression ratio ────────────────────────
dd if=/dev/zero of=/EMPTY bs=1M 2>/dev/null || true
rm -f /EMPTY
sync
