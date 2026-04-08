#!/usr/bin/env bash
# attach-cdrom.sh
# Attach Glance-backed ISO(s) to a running Nova instance via libvirt.
# Must be run ON the compute node hosting the instance.
# Requires: openstack CLI, virsh, python3
#
# Usage: attach-cdrom.sh [VM_NAME] [IMAGE_NAME]
#   Prompts interactively for any omitted argument.
#   Up to 2 ISOs can be attached per invocation.
set -euo pipefail

NFS_GLANCE_MOUNT="/var/opt/imagelibrary/data/glance"
CDROM_DEVS=(sdb sdc sdd sde)  # candidate target devices, in preference order

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Resolve a Nova instance name to its UUID.
# Prints UUID to stdout; disambiguation menu goes to stderr.
resolve_server_uuid() {
  local name="$1"
  local json count

  json=$(openstack server list --name "$name" -f json -c ID -c Name 2>/dev/null)
  count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$json")

  if [[ "$count" -eq 0 ]]; then
    echo "ERROR: No Nova instance found with name '$name'" >&2
    return 1
  elif [[ "$count" -eq 1 ]]; then
    python3 -c "import sys,json; print(json.load(sys.stdin)[0]['ID'])" <<< "$json"
  else
    echo "Multiple instances match '$name':" >&2
    python3 -c "
import sys, json
for i, s in enumerate(json.load(sys.stdin), 1):
    print(f'  {i}) {s[\"ID\"]}  {s[\"Name\"]}')
" <<< "$json" >&2
    local choice
    read -rp "Select instance [1-${count}]: " choice </dev/tty
    python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[int(sys.argv[1]) - 1]['ID'])
" "$choice" <<< "$json"
  fi
}

# Resolve a Glance image name to its UUID.
resolve_image_uuid() {
  local name="$1"
  local json count

  json=$(openstack image list --name "$name" -f json -c ID -c Name 2>/dev/null)
  count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$json")

  if [[ "$count" -eq 0 ]]; then
    echo "ERROR: No Glance image found with name '$name'" >&2
    return 1
  elif [[ "$count" -eq 1 ]]; then
    python3 -c "import sys,json; print(json.load(sys.stdin)[0]['ID'])" <<< "$json"
  else
    echo "Multiple images match '$name':" >&2
    python3 -c "
import sys, json
for i, s in enumerate(json.load(sys.stdin), 1):
    print(f'  {i}) {s[\"ID\"]}  {s[\"Name\"]}')
" <<< "$json" >&2
    local choice
    read -rp "Select image [1-${count}]: " choice </dev/tty
    python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[int(sys.argv[1]) - 1]['ID'])
" "$choice" <<< "$json"
  fi
}

# Return the first candidate device not already in use by the domain.
next_free_dev() {
  local domain="$1"
  local used_devs
  used_devs=$(virsh domblklist "$domain" --details | awk 'NR>2 {print $3}')
  for dev in "${CDROM_DEVS[@]}"; do
    if ! grep -qx "$dev" <<< "$used_devs" 2>/dev/null; then
      echo "$dev"
      return 0
    fi
  done
  echo "ERROR: No free cdrom target devices available (tried: ${CDROM_DEVS[*]})" >&2
  return 1
}

attach_iso() {
  local domain="$1" instance_uuid="$2" image_uuid="$3" target_dev="$4"
  local iso_path="${NFS_GLANCE_MOUNT}/${image_uuid}"

  if [[ ! -f "$iso_path" ]]; then
    echo "ERROR: Glance image not found on NFS at $iso_path" >&2
    return 1
  fi

  echo "Attaching $iso_path to domain $domain as $target_dev (cdrom, readonly) ..."
  virsh attach-disk "$domain" "$iso_path" "$target_dev" \
    --type cdrom \
    --mode readonly \
    --driver qemu \
    --subdriver raw \
    --live

  echo "Attached successfully."
  echo "  INSTANCE=${instance_uuid}"
  echo "  GLANCE_IMAGE=${image_uuid}"
  echo "  DOMAIN=${domain}"
  echo "  DEVICE=/dev/${target_dev}"
  echo "  ISO=${iso_path}"
}

# ---------------------------------------------------------------------------
# Resolve VM
# ---------------------------------------------------------------------------

VM_NAME="${1:-}"
FIRST_IMAGE_NAME="${2:-}"

[[ -z "$VM_NAME" ]] && read -rp "VM name: " VM_NAME </dev/tty

INSTANCE_UUID=$(resolve_server_uuid "$VM_NAME")
echo "Resolved instance: $INSTANCE_UUID"

DOMAIN=$(virsh list --all | awk -v uuid="$INSTANCE_UUID" '$0 ~ uuid {print $2}')
if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: No libvirt domain found for instance $INSTANCE_UUID on this host" >&2
  exit 1
fi
echo "Resolved domain:   $DOMAIN"

# ---------------------------------------------------------------------------
# Attach ISOs (up to 2)
# ---------------------------------------------------------------------------

ATTACHED=0

for iso_slot in 1 2; do
  if [[ $iso_slot -eq 1 ]]; then
    IMAGE_NAME="${FIRST_IMAGE_NAME:-}"
    [[ -z "$IMAGE_NAME" ]] && read -rp "ISO image name: " IMAGE_NAME </dev/tty
  else
    yn=""
    read -rp "Attach a second ISO? [y/N]: " yn </dev/tty
    [[ "$yn" =~ ^[Yy]$ ]] || break
    IMAGE_NAME=""
    read -rp "Second ISO image name: " IMAGE_NAME </dev/tty
  fi

  IMAGE_UUID=$(resolve_image_uuid "$IMAGE_NAME")
  echo "Resolved image:    $IMAGE_UUID"

  TARGET_DEV=$(next_free_dev "$DOMAIN")
  attach_iso "$DOMAIN" "$INSTANCE_UUID" "$IMAGE_UUID" "$TARGET_DEV"
  ATTACHED=$((ATTACHED + 1))
done

echo ""
echo "Done. ${ATTACHED} ISO(s) attached to ${DOMAIN}."
