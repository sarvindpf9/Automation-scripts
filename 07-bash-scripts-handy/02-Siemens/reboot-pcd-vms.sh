#!/usr/bin/env bash
# reboot-pcd-vms.sh
# Resolves one or more VM names to UUIDs (across all projects) and reboots them.
# Requires OpenStack credentials with admin scope (for --all-projects lookup).
set -euo pipefail


# Usage

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [OPTIONS] <vm-name> [vm-name ...]

Resolves each VM name to its UUID (searching all projects) and reboots it.
Requires admin-scoped OpenStack credentials.

Options:
  --hard        Perform a hard (power-cycle) reboot instead of soft (default: soft)
  --wait        Wait for each VM to return to ACTIVE state before continuing
  --timeout N   Seconds to wait per VM when --wait is used (default: 120)
  -h, --help    Show this help message

Examples:
  $(basename "$0") my-vm-01
  $(basename "$0") vm-a vm-b vm-c
  $(basename "$0") --hard --wait vm-prod-01
EOF
  exit 1
}


# Dependency check
for cmd in openstack awk column; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

# Argument parsing
REBOOT_TYPE="SOFT"
WAIT=false
TIMEOUT=90
VM_NAMES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hard)        REBOOT_TYPE="HARD"; shift ;;
    --wait)        WAIT=true; shift ;;
    --timeout)     TIMEOUT="$2"; shift 2 ;;
    -h|--help)     usage ;;
    -*)            echo "Error: unknown option '$1'" >&2; usage ;;
    *)             VM_NAMES+=("$1"); shift ;;
  esac
done

if (( ${#VM_NAMES[@]} == 0 )); then
  echo "Error: at least one VM name is required." >&2
  usage
fi


# Helpers
SEP="=================================================================="

log()  { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] ERROR: $*" >&2; }

# Resolve a VM name to its UUID across all projects.
# Exits non-zero and prints an error if 0 or >1 match is found.
# Sets globals VM_UUID_MAP and VM_PROJECT_MAP for the resolved entry.
resolve_vm() {
  local name="$1"
  local matches
  matches=$(
    openstack server list \
      --all-projects \
      --name "^${name}$" \
      -f value -c ID -c Name -c "Project ID" \
      --insecure 2>/dev/null
  )

  local count
  count=$(echo "$matches" | grep -c . || true)

  if [[ $count -eq 0 ]]; then
    err "VM name '${name}' not found in any project."
    return 1
  fi

  if [[ $count -gt 1 ]]; then
    err "VM name '${name}' matches ${count} instances across projects:"
    echo "$matches" >&2
    err "Provide a more specific name or use the UUID directly."
    return 1
  fi

  local uuid project_id project_name
  uuid=$(echo "$matches" | awk '{print $1}')
  project_id=$(echo "$matches" | awk '{print $3}')
  project_name=$(openstack project show "$project_id" -f value -c name --insecure 2>/dev/null || echo "$project_id")

  VM_UUID_MAP["$name"]="$uuid"
  VM_PROJECT_MAP["$name"]="$project_name"
}

# Print a status block for one VM. project_name is optional display context.
show_vm_status() {
  local uuid="$1" project_name="${2:-}"
  local raw
  raw=$(openstack server show "$uuid" \
    -f value \
    -c id \
    -c name \
    -c status \
    -c OS-EXT-STS:task_state \
    -c OS-EXT-STS:power_state \
    -c OS-EXT-AZ:availability_zone \
    -c updated \
    --insecure 2>/dev/null) || { echo "  (unable to retrieve VM details)" ; return; }

  local fields=("id" "name" "status" "task_state" "power_state" "availability_zone" "updated")
  local i=0
  while IFS= read -r line; do
    printf "  %-22s %s\n" "${fields[$i]}:" "$line"
    (( i++ )) || true
  done <<< "$raw"
  [[ -n "$project_name" ]] && printf "  %-22s %s\n" "project:" "$project_name"
}

# Poll until VM reaches ACTIVE, moves to a terminal bad state, or the cap expires.
# Exits as soon as the state is known — does not wait out the full timeout.
wait_for_active() {
  local uuid="$1"
  local deadline=$(( $(date +%s) + TIMEOUT ))
  local status="" prev_status="" elapsed

  log "Polling VM ${uuid} (max ${TIMEOUT}s)..."
  while true; do
    status=$(openstack server show "$uuid" -f value -c status --insecure 2>/dev/null || true)
    status="${status:-API_UNAVAILABLE}"

    # Print a line only when state changes (avoids log spam)
    if [[ "$status" != "$prev_status" ]]; then
      elapsed=$(( $(date +%s) - (deadline - TIMEOUT) ))
      log "  [+${elapsed}s] state: ${status}"
      prev_status="$status"
    fi

    case "$status" in
      ACTIVE)
        log "VM ${uuid} is ACTIVE."
        return 0
        ;;
      ERROR)
        err "VM ${uuid} is in ERROR state — skipping further wait."
        return 1
        ;;
      DELETED|SOFT_DELETED)
        err "VM ${uuid} is ${status} — skipping further wait."
        return 1
        ;;
      REBOOT|HARD_REBOOT|BUILD|SHUTOFF|RESIZE|VERIFY_RESIZE|API_UNAVAILABLE)
        # Transient or recoverable — keep waiting
        ;;
      *)
        log "  Warning: unexpected state '${status}' — continuing to poll."
        ;;
    esac

    if (( $(date +%s) >= deadline )); then
      err "Timed out after ${TIMEOUT}s. Last known state: ${status}. Continuing to next VM."
      return 1
    fi

    sleep 10
  done
}

# Resolve all names to UUIDs 
echo ""
echo "$SEP"
log "Resolving ${#VM_NAMES[@]} VM name(s) to UUIDs (searching all projects)..."
echo "$SEP"

declare -A VM_UUID_MAP     # name -> uuid
declare -A VM_PROJECT_MAP  # name -> project/tenant name
FAILED_RESOLVE=()

for name in "${VM_NAMES[@]}"; do
  if resolve_vm "$name"; then
    log "  ${name}  -->  ${VM_UUID_MAP[$name]}  (project: ${VM_PROJECT_MAP[$name]})"
  else
    FAILED_RESOLVE+=("$name")
  fi
done

if (( ${#FAILED_RESOLVE[@]} > 0 )); then
  err "Failed to resolve the following VM name(s): ${FAILED_RESOLVE[*]}"
  err "Aborting — no reboots performed."
  exit 1
fi


# Reboot each VM sequentially
echo ""
echo "$SEP"
log "Reboot type: ${REBOOT_TYPE} | Wait for ACTIVE: ${WAIT} | VMs: ${#VM_NAMES[@]}"
echo "$SEP"

RESULTS=()   # accumulate "name|uuid|project|result" for the final report

for name in "${VM_NAMES[@]}"; do
  uuid="${VM_UUID_MAP[$name]}"
  project="${VM_PROJECT_MAP[$name]}"
  echo ""
  log ">>> Processing VM: ${name} (${uuid})  project: ${project}"

  log "Pre-reboot status:"
  show_vm_status "$uuid" "$project"

  log "Issuing ${REBOOT_TYPE} reboot..."
  if openstack server reboot --${REBOOT_TYPE,,} "$uuid" --insecure 2>/dev/null; then
    log "Reboot command accepted for ${name}."
    result="REBOOT_ISSUED"
  else
    err "Reboot command failed for ${name} (${uuid}) — continuing to next VM."
    result="REBOOT_FAILED"
    RESULTS+=("${name}|${uuid}|${project}|${result}")
    continue
  fi

  if $WAIT; then
    wait_for_active "$uuid" && result="SUCCESS" || result="WAIT_FAILED"
  fi

  log "Post-reboot status:"
  show_vm_status "$uuid" "$project"

  RESULTS+=("${name}|${uuid}|${project}|${result}")
done

#Summary report

echo ""
log "REBOOT SUMMARY"
echo ""
for entry in "${RESULTS[@]}"; do
  IFS='|' read -r n u p r <<< "$entry"
  echo "  VM      : $n"
  echo "  UUID    : $u"
  echo "  Project : $p"
  echo "  Result  : $r"
  echo ""
done
