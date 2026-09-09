#!/usr/bin/env bash
# launch-win-boot-vm.sh
# Builds the volumes for a Windows boot-from-volume install (install ISO,
# virtio driver ISO, blank OS target), creates a port on the given network,
# and launches the VM attached to that port via openstack CLI.
#
# Usage: ./launch-win-boot-vm.sh <windows-iso-name-or-id> <virtio-win-iso-name-or-id> <availability-zone-name> <volume-type> <vm-name> <network-name-or-id>

set -Eeuo pipefail

usage() {
  echo "Usage: $0 <windows-iso-name-or-id> <virtio-win-iso-name-or-id> <availability-zone-name> <volume-type> <vm-name> <network-name-or-id>" >&2
  exit 1
}

# --- guardrails --------------------------------------------------------
# Report the failing command and line instead of a bare non-zero exit, so a
# failure anywhere below (including inside `openstack` itself) is traceable.
trap 'echo "ERROR: aborted (exit $?) at line ${LINENO}: ${BASH_COMMAND}" >&2' ERR

command -v openstack >/dev/null 2>&1 || { echo "ERROR: 'openstack' CLI not found in PATH." >&2; exit 1; }

[[ $# -eq 6 ]] || usage

WINDOWS_ISO="$1"
VIRTIO_ISO="$2"
AVAILABILITY_ZONE="$3"
VOLUME_TYPE="$4"
VM_NAME="$5"
NETWORK_NAME_OR_UUID="$6"

# Preserve the original defaults while allowing callers to use another flavor
# or enable certificate verification without changing the positional interface.
OPENSTACK_FLAVOR="${OPENSTACK_FLAVOR:-m1.xlarge}"
OPENSTACK_TLS_ARG="--insecure"
if [[ "${OPENSTACK_VERIFY_TLS:-false}" == true ]]; then
  OPENSTACK_TLS_ARG=""
fi

for arg_name in WINDOWS_ISO VIRTIO_ISO AVAILABILITY_ZONE VOLUME_TYPE VM_NAME NETWORK_NAME_OR_UUID; do
  [[ -n "${!arg_name}" ]] || { echo "ERROR: ${arg_name} must not be empty." >&2; usage; }
done

# Use a per-run suffix so retries and concurrent builds cannot resolve a
# different resource that happens to have the same name.
RUN_SUFFIX="$(date -u +%Y%m%d%H%M%S)-$$"
WINDOWS_INSTALL_VOLUME="${VM_NAME}-windows-installation-${RUN_SUFFIX}"
VIRTIO_DRIVER_VOLUME="${VM_NAME}-virtio-driver-${RUN_SUFFIX}"
WINDOWS_OS_TARGET_VOLUME="${VM_NAME}-windows-os-target-${RUN_SUFFIX}"
PORT_NAME="${VM_NAME}-port-${RUN_SUFFIX}"

PORT_ID=""
CREATED_VOLUME_IDS=()
PROVISIONING_COMPLETE=false

# Remove only resources created by this run when provisioning aborts. UUIDs
# are used deliberately so similarly named resources are never affected.
cleanup_on_failure() {
  local exit_code=$?
  local volume_id

  if [[ $exit_code -eq 0 || "$PROVISIONING_COMPLETE" == true ]]; then
    return
  fi

  echo "==> Cleaning up resources created by this failed run" >&2
  for volume_id in "${CREATED_VOLUME_IDS[@]}"; do
    openstack volume delete "$volume_id" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"} >/dev/null 2>&1 || \
      echo "WARNING: could not delete volume ${volume_id}; remove it manually." >&2
  done
  if [[ -n "$PORT_ID" ]]; then
    openstack port delete "$PORT_ID" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"} >/dev/null 2>&1 || \
      echo "WARNING: could not delete port ${PORT_ID}; remove it manually." >&2
  fi
}

trap cleanup_on_failure EXIT

# Run a command that produces no output we need; exit with a clear message
# naming the step on failure instead of a bare `set -e` abort.
run_step() {
  local description="$1"; shift
  echo "==> ${description}"
  if ! "$@"; then
    echo "ERROR: step failed: ${description}" >&2
    exit 1
  fi
}

# Run a command whose stdout must be captured (e.g. -f value -c id lookups),
# failing with a clear message (while leaving the command's stderr separate)
# or returns empty output.
capture_step() {
  local description="$1"; shift
  local output
  if ! output=$("$@"); then
    echo "ERROR: step failed: ${description}" >&2
    exit 1
  fi
  if [[ -z "$output" ]]; then
    echo "ERROR: step returned no output: ${description}" >&2
    exit 1
  fi
  echo "$output"
}

# Resolve a glance image name/id to its id, erroring out if it doesn't exist.
resolve_image_id() {
  local image_ref="$1"
  capture_step "resolve image '${image_ref}'" openstack image show "$image_ref" -f value -c id ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"}
}

# Resolve a network name/id to its id, erroring out if it doesn't exist.
resolve_network_id() {
  local network_ref="$1"
  capture_step "resolve network '${network_ref}'" openstack network show "$network_ref" -f value -c id ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"}
}

echo "==> Checking Windows installation ISO: ${WINDOWS_ISO}"
WINDOWS_ISO_ID=$(resolve_image_id "$WINDOWS_ISO")

echo "==> Checking virtio driver ISO: ${VIRTIO_ISO}"
VIRTIO_ISO_ID=$(resolve_image_id "$VIRTIO_ISO")

echo "==> Resolving network: ${NETWORK_NAME_OR_UUID}"
NETWORK_ID=$(resolve_network_id "$NETWORK_NAME_OR_UUID")

PORT_ID=$(capture_step "create port '${PORT_NAME}' on network '${NETWORK_NAME_OR_UUID}'" \
  openstack port create --network "$NETWORK_ID" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"} -f value -c id "$PORT_NAME")

INSTALL_VOLUME_ID=$(capture_step "create ${WINDOWS_INSTALL_VOLUME}" \
  openstack volume create --image "$WINDOWS_ISO_ID" --size 10 --type "$VOLUME_TYPE" \
  --bootable --wait -f value -c id "$WINDOWS_INSTALL_VOLUME" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"})
CREATED_VOLUME_IDS+=("$INSTALL_VOLUME_ID")

DRIVER_VOLUME_ID=$(capture_step "create ${VIRTIO_DRIVER_VOLUME}" \
  openstack volume create --image "$VIRTIO_ISO_ID" --size 2 --type "$VOLUME_TYPE" \
  --wait -f value -c id "$VIRTIO_DRIVER_VOLUME" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"})
CREATED_VOLUME_IDS+=("$DRIVER_VOLUME_ID")

TARGET_VOLUME_ID=$(capture_step "create ${WINDOWS_OS_TARGET_VOLUME}" \
  openstack volume create --size 40 --type "$VOLUME_TYPE" --bootable \
  --wait -f value -c id "$WINDOWS_OS_TARGET_VOLUME" ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"})
CREATED_VOLUME_IDS+=("$TARGET_VOLUME_ID")

# Image properties required for Windows to boot correctly from a raw volume
# (UEFI-style boot menu, q35 chipset, SATA cdrom, virtio disk/scsi, qemu-ga).
run_step "Setting boot image properties on ${WINDOWS_OS_TARGET_VOLUME}" \
  openstack volume set \
  --image-property hw_boot_menu=true \
  --image-property hw_firmware_type=uefi \
  --image-property hw_machine_type=q35 \
  --image-property hw_cdrom_bus=sata \
  --image-property hw_disk_bus=scsi \
  --image-property hw_scsi_model=virtio-scsi \
  --image-property os_type=windows \
  --image-property hw_qemu_guest_agent=yes \
  --image-property os_require_quiesce=yes \
  ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"} \
  "$TARGET_VOLUME_ID"

run_step "Launching VM: ${VM_NAME}" \
  openstack server create ${OPENSTACK_TLS_ARG:+"$OPENSTACK_TLS_ARG"} --flavor "$OPENSTACK_FLAVOR" --port "$PORT_ID" \
  --block-device source_type=volume,uuid="$TARGET_VOLUME_ID",destination_type=volume,device_type=disk,boot_index=0 \
  --block-device source_type=volume,uuid="$INSTALL_VOLUME_ID",destination_type=volume,device_type=cdrom,boot_index=1 \
  --block-device source_type=volume,uuid="$DRIVER_VOLUME_ID",destination_type=volume,device_type=cdrom,boot_index=-1 \
  --availability-zone "$AVAILABILITY_ZONE" \
  "$VM_NAME"

PROVISIONING_COMPLETE=true
echo "==> VM '${VM_NAME}' creation request submitted successfully."
