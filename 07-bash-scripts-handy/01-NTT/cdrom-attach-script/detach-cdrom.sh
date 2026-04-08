#!/usr/bin/env bash
# detach-cdrom.sh
# Detach a cdrom device from a running Nova instance via libvirt.
# Must be run ON the compute node hosting the instance.
# Requires: openstack CLI, virsh, python3
#
# Usage: detach-cdrom.sh <VM_NAME>
#   If the name matches multiple instances, a selection menu is shown.
#   If multiple cdrom devices are attached, a selection menu is shown.
set -euo pipefail

VM_NAME="${1:?Usage: $0 <VM_NAME>}"

# ---------------------------------------------------------------------------
# Resolve instance UUID
# ---------------------------------------------------------------------------

json=$(openstack server list --name "$VM_NAME" -f json -c ID -c Name 2>/dev/null)
count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$json")

if [[ "$count" -eq 0 ]]; then
  echo "ERROR: No Nova instance found with name '$VM_NAME'" >&2
  exit 1
elif [[ "$count" -eq 1 ]]; then
  INSTANCE_UUID=$(python3 -c "import sys,json; print(json.load(sys.stdin)[0]['ID'])" <<< "$json")
else
  echo "Multiple instances match '$VM_NAME':" >&2
  python3 -c "
import sys, json
for i, s in enumerate(json.load(sys.stdin), 1):
    print(f'  {i}) {s[\"ID\"]}  {s[\"Name\"]}')
" <<< "$json" >&2
  read -rp "Select instance [1-${count}]: " choice </dev/tty
  INSTANCE_UUID=$(python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[int(sys.argv[1]) - 1]['ID'])
" "$choice" <<< "$json")
fi

echo "Resolved instance: $INSTANCE_UUID"

# ---------------------------------------------------------------------------
# Resolve libvirt domain
# ---------------------------------------------------------------------------

DOMAIN=$(virsh list --all | awk -v uuid="$INSTANCE_UUID" '$0 ~ uuid {print $2}')
if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: No libvirt domain found for instance $INSTANCE_UUID on this host" >&2
  exit 1
fi

echo "Resolved domain:   $DOMAIN"

# ---------------------------------------------------------------------------
# Discover attached cdrom devices
# ---------------------------------------------------------------------------

# domblklist --details columns: Type  Device  Target  Source  (header on rows 1-2)
mapfile -t CDROM_DEVS < <(virsh domblklist "$DOMAIN" --details | awk 'NR>2 && $2=="cdrom" {print $3}')

if [[ ${#CDROM_DEVS[@]} -eq 0 ]]; then
  echo "ERROR: No cdrom devices attached to domain $DOMAIN" >&2
  exit 1
elif [[ ${#CDROM_DEVS[@]} -eq 1 ]]; then
  TARGET_DEV="${CDROM_DEVS[0]}"
  echo "Found cdrom device: $TARGET_DEV"
else
  echo "Multiple cdrom devices attached to $DOMAIN:" >&2
  for i in "${!CDROM_DEVS[@]}"; do
    echo "  $((i+1))) ${CDROM_DEVS[$i]}" >&2
  done
  read -rp "Select device to detach [1-${#CDROM_DEVS[@]}]: " choice </dev/tty
  TARGET_DEV="${CDROM_DEVS[$((choice-1))]}"
fi

# ---------------------------------------------------------------------------
# Detach
# ---------------------------------------------------------------------------

echo "Detaching $TARGET_DEV (cdrom) from domain $DOMAIN ..."
virsh detach-disk "$DOMAIN" "$TARGET_DEV" --live

echo "Detached successfully."
echo "  INSTANCE=$INSTANCE_UUID"
echo "  DOMAIN=$DOMAIN"
echo "  DEVICE=/dev/$TARGET_DEV"
echo "  NOTE: Glance image on NFS is unaffected."
