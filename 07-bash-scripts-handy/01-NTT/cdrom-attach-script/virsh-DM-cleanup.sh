#!/usr/bin/env bash
set -euo pipefail

VM_UUID="${1:-}"

# ── helpers ───────────────────────────────────────────────────────────────────
die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "  $*"; }

# ── validate input ────────────────────────────────────────────────────────────
[[ -z "$VM_UUID" ]] && die "Usage: $0 <vm-uuid>"
command -v virsh     >/dev/null 2>&1 || die "'virsh' not found"
command -v dmsetup   >/dev/null 2>&1 || die "'dmsetup' not found"
command -v multipath >/dev/null 2>&1 || die "'multipath' not found"

# ── 1. resolve dm devices from virsh blklist ──────────────────────────────────
echo
echo "Block devices for VM: $VM_UUID"
echo "──────────────────────────────────────────────────"

blklist_output=$(virsh domblklist "$VM_UUID" --details 2>/dev/null) \
  || die "Could not query VM '$VM_UUID'. Check UUID and libvirt access."

mapfile -t dm_devices < <(
  awk '/\/dev\/dm-/ { print $NF }' <<< "$blklist_output"
)

[[ ${#dm_devices[@]} -eq 0 ]] && die "No /dev/dm-* devices found for VM '$VM_UUID'."

for dev in "${dm_devices[@]}"; do
  info "$dev"
done

# ── 2. multipath status (VM disks only) ───────────────────────────────────────
echo
echo "Multipath status (VM disks only)"
echo "──────────────────────────────────────────────────"
for dev in "${dm_devices[@]}"; do
  dm_name=$(basename "$dev")
  dm_path="/dev/${dm_name}"

  if [[ ! -b "$dm_path" ]]; then
    info "SKIP  $dm_path — not a block device"
    continue
  fi

  mp_name=$(dmsetup info -c --noheadings -o name "$dm_path" 2>/dev/null) \
    || { info "WARN  $dm_path — could not resolve map name"; continue; }

  echo
  info "[$dm_path  →  $mp_name]"
  multipath -ll "$mp_name" 2>/dev/null \
    || info "WARN  no multipath entry for '$mp_name'"
done

# ── 3. drop queue on each dm device ──────────────────────────────────────────
echo
echo "Setting fail_if_no_path on dm devices"
echo "──────────────────────────────────────────────────"
for dev in "${dm_devices[@]}"; do
  dm_name=$(basename "$dev")
  dm_path="/dev/${dm_name}"

  [[ ! -b "$dm_path" ]] && continue

  info "dmsetup message $dm_path 0 fail_if_no_path"
  if dmsetup message "$dm_path" 0 "fail_if_no_path" 2>/dev/null; then
    info "OK    $dm_path"
  else
    info "WARN  $dm_path — dmsetup message failed (check dm-mpath target type)"
  fi
done

# ── 4. confirm before destroy ─────────────────────────────────────────────────
echo
echo "──────────────────────────────────────────────────"
read -r -p "Destroy VM '$VM_UUID' with virsh destroy? [yes/N]: " confirm

if [[ "${confirm,,}" != "yes" ]]; then
  info "Aborted. VM not destroyed."
  exit 0
fi

virsh destroy "$VM_UUID" 2>/dev/null || die "virsh destroy failed for '$VM_UUID'."
info "VM '$VM_UUID' destroyed."
echo
