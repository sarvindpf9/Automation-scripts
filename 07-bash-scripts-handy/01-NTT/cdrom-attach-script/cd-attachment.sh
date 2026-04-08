#!/usr/bin/env bash
# cd-attachment.sh
# Orchestrator: resolve a VM by IP or name, identify its hypervisor, then
# attach or detach Glance-backed ISO(s) via virsh (sudo) over SSH.
#
# Usage:
#   cd-attachment.sh --action attach --vm-ip <IP>   --user <SSH_USER> \
#                    --image-uuid <UUID> [--image-uuid2 <UUID>]
#   cd-attachment.sh --action attach --vm-name <NAME> --user <SSH_USER> \
#                    --image-uuid <UUID> [--image-uuid2 <UUID>]
#   cd-attachment.sh --action detach --vm-ip <IP>   --user <SSH_USER>
#   cd-attachment.sh --action detach --vm-name <NAME> --user <SSH_USER>
#
# Requires (locally):  openstack CLI, ssh, python3
# Requires (hypervisor): virsh (invoked via sudo), access to NFS Glance mount
set -euo pipefail

NFS_GLANCE_MOUNT="/var/opt/imagelibrary/data/glance"
CDROM_CANDIDATES=(sdm sdn sdo sdp)  # preference order for new cdrom targets (sdm+ avoids conflicts with primary/data disks)
SSH_OPTS=(-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10)

# ---------------------------------------------------------------------------
# Usage / argument parsing
# ---------------------------------------------------------------------------

usage() {
  cat >&2 <<EOF
Usage:
  $(basename "$0") --action attach { --vm-ip <IP> | --vm-name <NAME> } --user <SSH_USER> \\
                    --image-uuid <UUID> [--image-uuid2 <UUID>]
  $(basename "$0") --action detach { --vm-ip <IP> | --vm-name <NAME> } --user <SSH_USER> [--device <DEV>]

Options:
  --action       attach or detach  (required)
  --vm-ip        IP address of the target VM  (mutually exclusive with --vm-name)
  --vm-name      Nova instance name of the target VM  (mutually exclusive with --vm-ip)
  --user         SSH username for the hypervisor  (required)
  --image-uuid   Glance image UUID to attach  (required for attach)
  --image-uuid2  Second Glance image UUID  (optional, attach only, max 2 total)
  --device       Device name to detach (e.g. sdm); detach only. Omit to detach all CDROMs.
  --help         Show this help
EOF
  exit 1
}

ACTION=""
VM_IP=""
VM_NAME=""
SSH_USER=""
IMAGE_UUID1=""
IMAGE_UUID2=""
DETACH_DEV=""

[[ $# -eq 0 ]] && usage

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action)      ACTION="$2";      shift 2 ;;
    --vm-ip)       VM_IP="$2";       shift 2 ;;
    --vm-name)     VM_NAME="$2";     shift 2 ;;
    --user)        SSH_USER="$2";    shift 2 ;;
    --image-uuid)  IMAGE_UUID1="$2"; shift 2 ;;
    --image-uuid2) IMAGE_UUID2="$2"; shift 2 ;;
    --device)      DETACH_DEV="$2";  shift 2 ;;
    --help|-h)     usage ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage
      ;;
  esac
done

[[ -z "$ACTION" ]]   && { echo "ERROR: --action is required"  >&2; usage; }
[[ -z "$SSH_USER" ]] && { echo "ERROR: --user is required"    >&2; usage; }
[[ -z "$VM_IP" && -z "$VM_NAME" ]] && {
  echo "ERROR: one of --vm-ip or --vm-name is required" >&2; usage
}
[[ -n "$VM_IP" && -n "$VM_NAME" ]] && {
  echo "ERROR: --vm-ip and --vm-name are mutually exclusive" >&2; usage
}
[[ "$ACTION" != "attach" && "$ACTION" != "detach" ]] && {
  echo "ERROR: --action must be 'attach' or 'detach'" >&2; usage
}
[[ "$ACTION" == "attach" && -z "$IMAGE_UUID1" ]] && {
  echo "ERROR: --image-uuid is required for attach" >&2; usage
}
[[ "$ACTION" == "attach" && -n "$DETACH_DEV" ]] && {
  echo "ERROR: --device is only valid with --action detach" >&2; usage
}

# ---------------------------------------------------------------------------
# OpenStack: resolve Nova instance UUID and name from IP
# ---------------------------------------------------------------------------

# Prints "UUID:NAME" to stdout; errors to stderr.
resolve_instance_by_ip() {
  local ip="$1"
  local json count

  echo "Resolving instance for IP ${ip} ..." >&2
  json=$(openstack server list --ip "$ip" -f json -c ID -c Name 2>/dev/null)
  json="${json:-[]}"
  count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$json")

  if [[ "$count" -eq 0 ]]; then
    echo "ERROR: No Nova instance found with IP '${ip}'" >&2
    return 1
  elif [[ "$count" -eq 1 ]]; then
    python3 -c "
import sys, json
d = json.load(sys.stdin)[0]
# Colon-delimited so caller can split on first ':' safely
print(d['ID'] + ':' + d['Name'])
" <<< "$json"
  else
    echo "Multiple instances match IP '${ip}':" >&2
    python3 -c "
import sys, json
for i, s in enumerate(json.load(sys.stdin), 1):
    print(f'  {i}) {s[\"ID\"]}  {s[\"Name\"]}', file=__import__(\"sys\").stderr)
" <<< "$json"
    local choice
    read -rp "Select instance [1-${count}]: " choice </dev/tty
    python3 -c "
import sys, json
data = json.load(sys.stdin)
d = data[int(sys.argv[1]) - 1]
print(d['ID'] + ':' + d['Name'])
" "$choice" <<< "$json"
  fi
}

# ---------------------------------------------------------------------------
# OpenStack: resolve Nova instance UUID and name from instance name
# ---------------------------------------------------------------------------

# Prints "UUID:NAME" to stdout; errors to stderr.
resolve_instance_by_name() {
  local name="$1"
  local json

  echo "Resolving instance by name '${name}' ..." >&2
  json=$(openstack server show "$name" -f json -c ID -c Name 2>/dev/null)
  if [[ -z "$json" ]]; then
    echo "ERROR: No Nova instance found with name '${name}'" >&2
    return 1
  fi
  python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['ID'] + ':' + d['Name'])
" <<< "$json"
}

# ---------------------------------------------------------------------------
# OpenStack: resolve hypervisor hostname and management IP from instance UUID
# ---------------------------------------------------------------------------

# Prints "HOSTNAME:IP" to stdout; errors to stderr.
# Resolves OS-EXT-SRV-ATTR:hypervisor_hostname from the server record, then
# cross-references against 'openstack hypervisor list --long' to obtain the
# Host IP — avoids a separate 'hypervisor show' call and handles environments
# where hypervisor_hostname differs from the compute service host label.
resolve_hypervisor() {
  local instance_uuid="$1"
  local hv_hostname hv_list hv_ip

  echo "Resolving hypervisor for instance ${instance_uuid} ..." >&2
  hv_hostname=$(openstack server show "$instance_uuid" \
    -f value -c "OS-EXT-SRV-ATTR:hypervisor_hostname" 2>/dev/null)
  if [[ -z "$hv_hostname" ]]; then
    echo "ERROR: Could not determine hypervisor_hostname for instance ${instance_uuid}" >&2
    echo "       Ensure your credentials have the 'admin' or 'reader' role on the project." >&2
    return 1
  fi
  echo "  Hypervisor hostname: ${hv_hostname}" >&2

  hv_list=$(openstack hypervisor list --long -f json 2>/dev/null)
  hv_list="${hv_list:-[]}"
  hv_ip=$(python3 -c "
import sys, json
data   = json.load(sys.stdin)
target = sys.argv[1]
for h in data:
    if h.get('Hypervisor Hostname') == target:
        print(h.get('Host IP', ''))
        sys.exit(0)
" "$hv_hostname" <<< "$hv_list")

  if [[ -z "$hv_ip" ]]; then
    echo "ERROR: No matching entry found in 'hypervisor list --long' for '${hv_hostname}'" >&2
    return 1
  fi
  echo "  Hypervisor IP:       ${hv_ip}" >&2

  echo "${hv_hostname}:${hv_ip}"
}

# ---------------------------------------------------------------------------
# Pre-checks: run before any virsh operation is attempted
# ---------------------------------------------------------------------------

# Verify the Nova instance is in a workable state (not DELETED / ERROR / SHELVED).
check_vm_exists() {
  local instance_uuid="$1"
  local status

  status=$(openstack server show "$instance_uuid" -f value -c status 2>/dev/null)
  if [[ -z "$status" ]]; then
    echo "PRE-CHECK FAILED: Instance ${instance_uuid} not found or not accessible." >&2
    return 1
  fi
  case "$status" in
    ACTIVE|SHUTOFF|PAUSED|SUSPENDED)
      echo "  [OK] VM state: ${status}"
      ;;
    *)
      echo "PRE-CHECK FAILED: VM ${instance_uuid} is in state '${status}'." \
           "Expected ACTIVE/SHUTOFF/PAUSED/SUSPENDED." >&2
      return 1
      ;;
  esac
}

# Verify a Glance image UUID exists and is active.
check_image_exists() {
  local image_uuid="$1"
  local status

  status=$(openstack image show "$image_uuid" -f value -c status 2>/dev/null)
  if [[ -z "$status" ]]; then
    echo "PRE-CHECK FAILED: Glance image ${image_uuid} not found or not accessible." >&2
    return 1
  fi
  if [[ "$status" != "active" ]]; then
    echo "PRE-CHECK FAILED: Glance image ${image_uuid} has status '${status}' (expected 'active')." >&2
    return 1
  fi
  echo "  [OK] Image ${image_uuid} status: ${status}"
}

# Verify the hypervisor is reachable via ICMP and SSH.
check_hypervisor_reachable() {
  local hv_ip="$1" user="$2"

  # ICMP reachability — a quick sanity check before attempting TCP/SSH
  if ! ping -c 1 -W 2 "$hv_ip" &>/dev/null; then
    echo "PRE-CHECK FAILED: Hypervisor ${hv_ip} is not reachable via ICMP." >&2
    return 1
  fi
  echo "  [OK] Hypervisor ${hv_ip} is reachable via ICMP."

  # SSH reachability — confirms port 22 is open and credentials work
  if ! ssh "${SSH_OPTS[@]}" "${user}@${hv_ip}" "true" 2>/dev/null; then
    echo "PRE-CHECK FAILED: Cannot SSH to ${hv_ip} as '${user}'." \
         "Check key/credentials and sshd on the hypervisor." >&2
    return 1
  fi
  echo "  [OK] SSH to ${user}@${hv_ip} succeeded."
}

# Orchestrate all pre-checks; called after resolution, before virsh operations.
# Args: hv_ip user instance_uuid [image_uuid1 [image_uuid2]]
run_prechecks() {
  local hv_ip="$1" user="$2" instance_uuid="$3"
  shift 3
  local image_uuids=("$@")  # empty for detach
  local failed=0

  echo ""
  echo "==> Running pre-checks ..."

  check_vm_exists "$instance_uuid"           || failed=1
  check_hypervisor_reachable "$hv_ip" "$user" || failed=1

  for image_uuid in "${image_uuids[@]}"; do
    check_image_exists "$image_uuid" || failed=1
  done

  if [[ "$failed" -ne 0 ]]; then
    echo ""
    echo "One or more pre-checks failed. Aborting." >&2
    exit 1
  fi

  echo "  All pre-checks passed."
  echo ""
}

# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

# Wrapper: run a command on the hypervisor via SSH.
ssh_run() {
  local hv_ip="$1" user="$2"
  shift 2
  ssh "${SSH_OPTS[@]}" "${user}@${hv_ip}" "$@"
}

# Find the libvirt domain name for a given Nova instance UUID on the hypervisor.
remote_resolve_domain() {
  local hv_ip="$1" user="$2" instance_uuid="$3"
  local domain
  # virsh list --all does not include the UUID in its output; iterate domain
  # names and resolve each via 'virsh domuuid', which Nova sets to the Nova
  # instance UUID at boot time.
  domain=$(ssh_run "$hv_ip" "$user" \
    "sudo virsh list --all --name | while IFS= read -r name; do
       [[ -z \"\$name\" ]] && continue
       if sudo virsh domuuid \"\$name\" 2>/dev/null | grep -qF '${instance_uuid}'; then
         echo \"\$name\"
         break
       fi
     done")

  if [[ -z "$domain" ]]; then
    echo "ERROR: No libvirt domain found for instance ${instance_uuid} on ${hv_ip}" >&2
    return 1
  fi
  echo "$domain"
}

# Return the first CDROM_CANDIDATES device not already in use by the domain.
remote_next_free_dev() {
  local hv_ip="$1" user="$2" domain="$3"
  local used_devs

  used_devs=$(ssh_run "$hv_ip" "$user" \
    "sudo virsh domblklist '${domain}' --details | awk 'NR>2 {print \$3}'")

  for dev in "${CDROM_CANDIDATES[@]}"; do
    if ! grep -qx "$dev" <<< "$used_devs" 2>/dev/null; then
      echo "$dev"
      return 0
    fi
  done

  echo "ERROR: No free cdrom target devices available (tried: ${CDROM_CANDIDATES[*]})" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Attach operation
# ---------------------------------------------------------------------------

do_attach() {
  local hv_ip="$1" user="$2" instance_uuid="$3" domain="$4"
  shift 4
  local image_uuids=("$@")  # 1 or 2 UUIDs passed as remaining args
  local attached=0

  for image_uuid in "${image_uuids[@]}"; do
    local iso_path="${NFS_GLANCE_MOUNT}/${image_uuid}"

    # Verify ISO is accessible on the hypervisor before attempting attach
    if ! ssh_run "$hv_ip" "$user" "[[ -f '${iso_path}' ]]"; then
      echo "ERROR: Glance image not found on NFS at ${iso_path} on ${hv_ip}" >&2
      return 1
    fi

    local target_dev
    target_dev=$(remote_next_free_dev "$hv_ip" "$user" "$domain")

    echo "Attaching ${iso_path} to domain ${domain} as ${target_dev} ..."
    ssh_run "$hv_ip" "$user" \
      "sudo virsh attach-disk '${domain}' '${iso_path}' '${target_dev}' \
         --type cdrom --mode readonly --driver qemu --subdriver raw --live"

    echo "Attached successfully."
    echo "  INSTANCE=${instance_uuid}"
    echo "  GLANCE_IMAGE=${image_uuid}"
    echo "  DOMAIN=${domain}"
    echo "  DEVICE=/dev/${target_dev}"
    echo "  ISO=${iso_path}"
    attached=$((attached + 1))
  done

  echo ""
  echo "Done. ${attached} ISO(s) attached to ${domain}."
}

# ---------------------------------------------------------------------------
# Detach operation
# ---------------------------------------------------------------------------

do_detach() {
  local hv_ip="$1" user="$2" instance_uuid="$3" domain="$4" target_dev="$5"
  local cdrom_devs_raw cdrom_devs detached=0

  # Discover cdrom devices attached to the domain on the remote hypervisor
  cdrom_devs_raw=$(ssh_run "$hv_ip" "$user" \
    "sudo virsh domblklist '${domain}' --details | awk 'NR>2 && \$2==\"cdrom\" {print \$3}'")

  if [[ -z "$cdrom_devs_raw" ]]; then
    echo "ERROR: No cdrom devices attached to domain ${domain}" >&2
    return 1
  fi

  mapfile -t cdrom_devs <<< "$cdrom_devs_raw"

  if [[ ${#cdrom_devs[@]} -gt 2 ]]; then
    # More than 2 shouldn't happen given attach enforces the limit, but guard anyway
    echo "ERROR: ${#cdrom_devs[@]} cdrom devices found on ${domain}; " \
         "expected at most 2. Investigate manually." >&2
    return 1
  fi

  # If a specific device was requested, validate it is a cdrom on this domain
  if [[ -n "$target_dev" ]]; then
    if ! printf '%s\n' "${cdrom_devs[@]}" | grep -qx "$target_dev"; then
      echo "ERROR: Device '${target_dev}' is not an attached cdrom on domain ${domain}." >&2
      echo "       Attached cdrom(s): ${cdrom_devs[*]}" >&2
      return 1
    fi
    cdrom_devs=("$target_dev")
  fi

  for dev in "${cdrom_devs[@]}"; do
    echo "Detaching ${dev} (cdrom) from domain ${domain} ..."
    ssh_run "$hv_ip" "$user" "sudo virsh detach-disk '${domain}' '${dev}' --live"
    echo "Detached successfully."
    echo "  INSTANCE=${instance_uuid}"
    echo "  DOMAIN=${domain}"
    echo "  DEVICE=/dev/${dev}"
    echo "  NOTE: Glance image on NFS is unaffected."
    detached=$((detached + 1))
  done

  echo ""
  echo "Done. ${detached} ISO(s) detached from ${domain}."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# 1. Resolve instance UUID and name from VM IP or instance name
if [[ -n "$VM_IP" ]]; then
  raw=$(resolve_instance_by_ip "$VM_IP")
else
  raw=$(resolve_instance_by_name "$VM_NAME")
fi
INSTANCE_UUID="${raw%%:*}"
INSTANCE_NAME="${raw#*:}"
echo "Instance:   ${INSTANCE_NAME} (${INSTANCE_UUID})"

# 2. Resolve hypervisor hostname and management IP
raw=$(resolve_hypervisor "$INSTANCE_UUID")
HV_HOST="${raw%%:*}"
HV_IP="${raw#*:}"
echo "Hypervisor: ${HV_HOST} (${HV_IP})"

# 3. Pre-checks
case "$ACTION" in
  attach)
    precheck_images=("$IMAGE_UUID1")
    [[ -n "$IMAGE_UUID2" ]] && precheck_images+=("$IMAGE_UUID2")
    run_prechecks "$HV_IP" "$SSH_USER" "$INSTANCE_UUID" "${precheck_images[@]}"
    ;;
  detach)
    run_prechecks "$HV_IP" "$SSH_USER" "$INSTANCE_UUID"
    ;;
esac

# 4. Resolve libvirt domain on hypervisor
DOMAIN=$(remote_resolve_domain "$HV_IP" "$SSH_USER" "$INSTANCE_UUID")
echo "Domain:     ${DOMAIN}"
echo ""

# 5. Execute requested action
case "$ACTION" in
  attach)
    image_list=("$IMAGE_UUID1")
    [[ -n "$IMAGE_UUID2" ]] && image_list+=("$IMAGE_UUID2")
    do_attach "$HV_IP" "$SSH_USER" "$INSTANCE_UUID" "$DOMAIN" "${image_list[@]}"
    ;;
  detach)
    do_detach "$HV_IP" "$SSH_USER" "$INSTANCE_UUID" "$DOMAIN" "$DETACH_DEV"
    ;;
esac
