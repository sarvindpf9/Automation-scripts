#!/usr/bin/env bash
set -euo pipefail

# detach-iso.sh — Detach a cdrom device from a running Nova instance via libvirt
# Must be run ON the compute node hosting the instance.
#
# Usage: detach-iso.sh <INSTANCE_UUID> <TARGET_DEV>
#
# Arguments:
#   INSTANCE_UUID      Nova instance UUID
#   TARGET_DEV         Device name to detach, e.g. sdb
#                      TARGET_DEV is mandatory — operator must know what was attached.

INSTANCE_UUID="${1:?Usage: $0 <INSTANCE_UUID> <TARGET_DEV>}"
TARGET_DEV="${2:?Usage: $0 <INSTANCE_UUID> <TARGET_DEV>}"

# Resolve Nova UUID to libvirt domain name
DOMAIN=$(virsh list --all | awk -v uuid="$INSTANCE_UUID" '$0 ~ uuid {print $2}')
if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: No libvirt domain found for instance $INSTANCE_UUID on this host" >&2
  exit 1
fi

# Confirm device is attached and is a cdrom type before detaching
DEVICE_TYPE=$(virsh domblklist "$DOMAIN" --details | awk -v dev="$TARGET_DEV" '$3 == dev {print $2}')
if [[ -z "$DEVICE_TYPE" ]]; then
  echo "ERROR: Device $TARGET_DEV is not attached to domain $DOMAIN" >&2
  exit 1
fi

if [[ "$DEVICE_TYPE" != "cdrom" ]]; then
  echo "ERROR: Device $TARGET_DEV on domain $DOMAIN is of type '$DEVICE_TYPE', not cdrom — refusing to detach" >&2
  exit 1
fi

# Detach cdrom device
echo "Detaching $TARGET_DEV (cdrom) from domain $DOMAIN ..."
virsh detach-disk "$DOMAIN" "$TARGET_DEV" --live

echo "Detached successfully."
echo "  INSTANCE=$INSTANCE_UUID"
echo "  DOMAIN=$DOMAIN"
echo "  DEVICE=/dev/$TARGET_DEV"
echo "  NOTE: Glance image on NFS is unaffected."