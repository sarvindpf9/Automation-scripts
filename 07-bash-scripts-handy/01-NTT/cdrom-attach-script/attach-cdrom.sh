#!/usr/bin/env bash
set -euo pipefail

# attach-cdrom.sh — Attach a Glance-backed ISO to a running Nova instance via libvirt
# Must be run ON the compute node hosting the instance.
# 
# Usage: attach-cdrom.sh <INSTANCE_UUID> <GLANCE_IMAGE_UUID> [TARGET_DEV]
#
# Arguments:
#   INSTANCE_UUID      Nova instance UUID
#   GLANCE_IMAGE_UUID  Glance image UUID of the uploaded ISO
#   TARGET_DEV         Target device name inside VM (default: sdb)
#                      Pick one not already occupied by Nova-managed disks.

INSTANCE_UUID="${1:?Usage: $0 <INSTANCE_UUID> <GLANCE_IMAGE_UUID> [TARGET_DEV]}"
GLANCE_IMAGE_UUID="${2:?Usage: $0 <INSTANCE_UUID> <GLANCE_IMAGE_UUID> [TARGET_DEV]}"
TARGET_DEV="${3:-sdb}"

NFS_GLANCE_MOUNT="/var/opt/imagelibrary/data/glance"   # e.g. the mount should be present on the compute node with the target image id present.
ISO_PATH="${NFS_GLANCE_MOUNT}/${GLANCE_IMAGE_UUID}"

# Validate file exist in the path
if [[ ! -f "$ISO_PATH" ]]; then
  echo "ERROR: Glance image not found on NFS at $ISO_PATH" >&2
  exit 1
fi

# Resolve Nova UUID to libvirt domain name
DOMAIN=$(virsh list --all | awk -v uuid="$INSTANCE_UUID" '$0 ~ uuid {print $2}')
if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: No libvirt domain found for instance $INSTANCE_UUID on this host" >&2
  exit 1
fi

# Verify target device is not already in use by this domain
if virsh domblklist "$DOMAIN" --details | awk '{print $3}' | grep -qx "$TARGET_DEV"; then
  echo "ERROR: Device $TARGET_DEV is already attached to domain $DOMAIN" >&2
  exit 1
fi

echo "Attaching $ISO_PATH to domain $DOMAIN as $TARGET_DEV (cdrom, readonly) ..."
virsh attach-disk "$DOMAIN" "$ISO_PATH" "$TARGET_DEV" \
  --type cdrom \
  --mode readonly \
  --driver qemu \
  --subdriver raw \
  --live

echo "Attached successfully."
echo "  INSTANCE=$INSTANCE_UUID"
echo "  GLANCE_IMAGE=$GLANCE_IMAGE_UUID"
echo "  DOMAIN=$DOMAIN"
echo "  DEVICE=/dev/$TARGET_DEV"
echo "  ISO=$ISO_PATH"