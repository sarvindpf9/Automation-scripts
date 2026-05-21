#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# ── Package installation ───────────────────────────────────────────────────────
apt-get update -y
apt-get install -y qemu-guest-agent
apt-get clean

# ── Enable qemu-guest-agent ────────────────────────────────────────────────────
systemctl enable qemu-guest-agent

# ── /etc/fstab — append user-supplied entries ──────────────────────────────────
# mount -a is intentionally NOT called. Entries are written into the image so the
# deployed instance can mount them at boot or on demand. The build VM never mounts
# them, preserving build host stability.
FSTAB_SRC="/tmp/fstab_entries.conf"
if [[ -f "${FSTAB_SRC}" ]]; then
  FSTAB_ENTRIES=$(grep -v '^\s*#' "${FSTAB_SRC}" | grep -v '^\s*$' || true)
  if [[ -n "${FSTAB_ENTRIES}" ]]; then
    printf '\n# ── Custom entries (appended by packer build) ──────────────────────────────\n' >> /etc/fstab
    printf '%s\n' "${FSTAB_ENTRIES}" >> /etc/fstab
    echo "fstab: appended $(echo "${FSTAB_ENTRIES}" | wc -l) entry(s)"
  else
    echo "fstab: no entries to append (config/fstab_entries.conf contains only comments)"
  fi
fi
rm -f "${FSTAB_SRC}"

# ── /etc/hosts — append user-supplied entries ──────────────────────────────────
HOSTS_SRC="/tmp/hosts_entries.conf"
if [[ -f "${HOSTS_SRC}" ]]; then
  HOSTS_ENTRIES=$(grep -v '^\s*#' "${HOSTS_SRC}" | grep -v '^\s*$' || true)
  if [[ -n "${HOSTS_ENTRIES}" ]]; then
    printf '\n# ── Custom entries (appended by packer build) ──────────────────────────────\n' >> /etc/hosts
    printf '%s\n' "${HOSTS_ENTRIES}" >> /etc/hosts
    echo "hosts: appended $(echo "${HOSTS_ENTRIES}" | wc -l) entry(s)"
  else
    echo "hosts: no entries to append (config/hosts_entries.conf contains only comments)"
  fi
fi
rm -f "${HOSTS_SRC}"
