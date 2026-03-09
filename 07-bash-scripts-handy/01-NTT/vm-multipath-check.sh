#!/usr/bin/env bash
set -euo pipefail

for cmd in virsh multipath awk grep sed; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

if ! mapfile -t vms < <(virsh list --name 2>/dev/null | sed '/^$/d'); then
  echo "Error: failed to list VMs via 'virsh list --name'." >&2
  exit 1
fi

if ((${#vms[@]} == 0)); then
  echo "No running VMs found via virsh."
  exit 0
fi

for vm in "${vms[@]}"; do
  echo ""
  echo "=================================================================="
  echo "VM: $vm"
  echo "-- domblklist --details --"
  domblk="$(virsh domblklist --details "$vm" || true)"
  echo "$domblk"

  mapfile -t dms < <(awk '{print $4}' <<<"$domblk" | grep -oE 'dm-[0-9]+' | sort -u)

  if ((${#dms[@]} == 0)); then
    echo "No dm-* sources found for $vm"
    continue
  fi

  echo "-- multipath context for dm devices --"
  for dm in "${dms[@]}"; do
    echo "------------------"
    echo ">>> $dm"
    multipath -ll | grep -A5 -E "\\b${dm}\\b" || echo "Not found in multipath -ll: $dm"
  done
done
