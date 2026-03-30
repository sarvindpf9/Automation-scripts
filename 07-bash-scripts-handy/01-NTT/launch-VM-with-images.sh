#!/usr/bin/env bash
# launch-VM-with-images.sh
# Provisions volumes from Windows ISO + VirtIO driver ISO images and launches
# a Windows VM on OpenStack / PCD.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [OPTIONS]

Required:
  -w, --windows-iso UUID     Windows ISO image UUID
  -v, --virtio-iso UUID      VirtIO driver ISO image UUID
  -a, --az ZONE              Availability zone (PCD cluster)
  -n, --vm-name NAME         VM name

Network attachment (exactly one required):
  --network UUID|NAME        Attach VM to this network name or UUID
  --port UUID                Attach VM to this port UUID

Optional:
  -t, --volume-type TYPE     Cinder volume type for all volumes (optional)
  -h, --help                 Show this help message
EOF
  exit 1
}

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
for cmd in openstack; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
WINDOWS_ISO_UUID=""
VIRTIO_ISO_UUID=""
AZ=""
VM_NAME=""
NET_ARG=""
NET_VAL=""
VOLUME_TYPE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -w|--windows-iso)   WINDOWS_ISO_UUID="$2"; shift 2 ;;
    -v|--virtio-iso)    VIRTIO_ISO_UUID="$2";  shift 2 ;;
    -a|--az)            AZ="$2";               shift 2 ;;
    -n|--vm-name)       VM_NAME="$2";          shift 2 ;;
    -t|--volume-type)   VOLUME_TYPE="$2";      shift 2 ;;
    --network)          NET_ARG="--network";   NET_VAL="$2"; shift 2 ;;
    --port)             NET_ARG="--port";      NET_VAL="$2"; shift 2 ;;
    -h|--help)          usage ;;
    *) echo "Error: unknown argument '$1'" >&2; usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
errors=()
[[ -z "$WINDOWS_ISO_UUID" ]] && errors+=("--windows-iso is required")
[[ -z "$VIRTIO_ISO_UUID"  ]] && errors+=("--virtio-iso is required")
[[ -z "$AZ"               ]] && errors+=("--az is required")
[[ -z "$VM_NAME"          ]] && errors+=("--vm-name is required")
[[ -z "$NET_ARG"          ]] && errors+=("exactly one of --network or --port is required")

if (( ${#errors[@]} > 0 )); then
  for err in "${errors[@]}"; do
    echo "Error: $err" >&2
  done
  usage
fi

# ---------------------------------------------------------------------------
# Unique suffix to avoid duplicate volume name collisions
# ---------------------------------------------------------------------------
SUFFIX="$(date +%Y%m%d%H%M%S)-$$"
VOL_TARGET="windows-os-target-${SUFFIX}"
VOL_INSTALL="windows-installation-${SUFFIX}"
VOL_VIRTIO="virtio-driver-${SUFFIX}"

echo "==> Volume name suffix: ${SUFFIX}"

# Log file written alongside the script; one entry per run
LOG_FILE="$(dirname "$0")/volume-registry.log"

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
log_volume() {
  local role="$1" name="$2" uuid="$3"
  printf "%s  vm=%-30s  role=%-10s  name=%-50s  uuid=%s\n" \
    "$(date '+%Y-%m-%dT%H:%M:%S')" "$VM_NAME" "$role" "$name" "$uuid" \
    >> "$LOG_FILE"
}

# Build optional --type flag (empty when not specified)
TYPE_ARG=()
[[ -n "$VOLUME_TYPE" ]] && TYPE_ARG=(--type "$VOLUME_TYPE")

# ---------------------------------------------------------------------------
# Volume creation
# ---------------------------------------------------------------------------
echo ""
echo "==> Creating ${VOL_INSTALL} (from Windows ISO, 10 GB)..."
openstack volume create \
  --image "$WINDOWS_ISO_UUID" \
  --size 10 \
  --bootable \
  "${TYPE_ARG[@]}" \
  "$VOL_INSTALL" \
  --insecure

echo ""
echo "==> Creating ${VOL_VIRTIO} (from VirtIO ISO, 2 GB)..."
openstack volume create \
  --image "$VIRTIO_ISO_UUID" \
  --size 2 \
  "${TYPE_ARG[@]}" \
  "$VOL_VIRTIO" \
  --insecure

echo ""
echo "==> Creating ${VOL_TARGET} (blank, 20 GB)..."
openstack volume create \
  --size 20 \
  --bootable \
  "${TYPE_ARG[@]}" \
  "$VOL_TARGET" \
  --insecure

# ---------------------------------------------------------------------------
# Set image properties on the target OS volume
# ---------------------------------------------------------------------------
echo ""
echo "==> Setting firmware / hardware image-properties on ${VOL_TARGET}..."
openstack volume set \
  --image-property hw_boot_menu=true \
  --image-property hw_firmware_type=uefi \
  --image-property hw_machine_type=q35 \
  --image-property hw_cdrom_bus=sata \
  --image-property hw_disk_bus=virtio \
  --image-property hw_scsi_model=virtio-scsi \
  --image-property os_secure_boot=required \
  --image-property os_type=windows \
  --image-property hw_video_model=qxl \
  "$VOL_TARGET" \
  --insecure

# ---------------------------------------------------------------------------
# Resolve volume IDs at runtime
# ---------------------------------------------------------------------------
echo ""
echo "==> Resolving volume IDs..."
TARGET_VOL_ID=$(openstack volume show "$VOL_TARGET"  -f value -c id --insecure)
INSTALL_VOL_ID=$(openstack volume show "$VOL_INSTALL" -f value -c id --insecure)
VIRTIO_VOL_ID=$(openstack volume show "$VOL_VIRTIO"  -f value -c id --insecure)

echo "    ${VOL_TARGET}  : $TARGET_VOL_ID"
echo "    ${VOL_INSTALL} : $INSTALL_VOL_ID"
echo "    ${VOL_VIRTIO}  : $VIRTIO_VOL_ID"

echo ""
echo "==> Logging volume names and UUIDs to ${LOG_FILE}..."
log_volume "os-target" "$VOL_TARGET"  "$TARGET_VOL_ID"
log_volume "win-iso"   "$VOL_INSTALL" "$INSTALL_VOL_ID"
log_volume "virtio-iso" "$VOL_VIRTIO" "$VIRTIO_VOL_ID"

# ---------------------------------------------------------------------------
# Launch VM
# ---------------------------------------------------------------------------
echo ""
echo "==> Launching VM '${VM_NAME}'..."
openstack server create \
  --insecure \
  --flavor m1.xlarge \
  "$NET_ARG" "$NET_VAL" \
  --block-device "source_type=volume,uuid=${TARGET_VOL_ID},destination_type=volume,device_type=disk,boot_index=0" \
  --block-device "source_type=volume,uuid=${INSTALL_VOL_ID},destination_type=volume,device_type=cdrom,boot_index=1" \
  --block-device "source_type=volume,uuid=${VIRTIO_VOL_ID},destination_type=volume,device_type=cdrom,boot_index=-1" \
  --availability-zone "$AZ" \
  "$VM_NAME"

echo ""
echo "==> Done. VM '${VM_NAME}' creation request submitted."
echo "    Monitor status with: openstack server show '${VM_NAME}' --insecure"
