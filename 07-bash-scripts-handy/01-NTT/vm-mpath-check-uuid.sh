#!/usr/bin/env bash
set -euo pipefail

for cmd in virsh multipath awk grep sed; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

if (($# != 1)); then
  echo "Usage: $0 <vm-uuid>" >&2
  exit 1
fi

vm="$1"

# Validate that the VM (UUID) exists and is known to virsh
if ! virsh dominfo "$vm" >/dev/null 2>&1; then
  echo "Error: VM with UUID or name '$vm' not found via virsh." >&2
  exit 1
fi

echo ""
echo "=================================================================="
echo "VM (UUID or name): $vm"
echo "-- domblklist --details --"
domblk="$(virsh domblklist --details "$vm" || true)"
echo "$domblk"

mapfile -t dms < <(awk '{print $4}' <<<"$domblk" | grep -oE 'dm-[0-9]+' | sort -u)

if ((${#dms[@]} == 0)); then
  echo "No dm-* sources found for $vm"
  exit 0
fi

echo "-- multipath context for dm devices --"
for dm in "${dms[@]}"; do
  echo "------------------"
  echo ">>> $dm"
  multipath -ll | grep -A5 -E "\\b${dm}\\b" || echo "Not found in multipath -ll: $dm"
done
