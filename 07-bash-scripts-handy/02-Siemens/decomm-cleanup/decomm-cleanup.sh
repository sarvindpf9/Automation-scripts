#!/usr/bin/env bash
# decomm-cleanup.sh — PCD node decommission helper
# Connects to each host with username/password, escalates to root via sudo,
# then runs the selected cleanup steps.
#
# Usage:
#   decomm-cleanup.sh -f hosts.txt -u <user> -p <password> [--check-pf9] [--fix-fstab] [--deauth] [--all]
#
# Options:
#   -f <file>       File containing one hostname/IP per line (required)
#   -u <user>       SSH user (required)
#   -p <password>   SSH password; also used for sudo (required)
#   --check-pf9     Run: dpkg -l | grep -i pf9
#   --fix-fstab     Comment out opt/data/instances and var/lib/glance/images in /etc/fstab
#   --unmount       Unmount /opt/data/instances and /var/lib/glance/images if currently mounted
#   --check-dirs    Report presence/absence of known PF9 artifact paths (highlighted)
#   --clean-dirs    Delete the PF9 artifact paths found by --check-dirs (DESTRUCTIVE)
#   --decommission  Run: pcdctl decommission-node --verbose --no-prompt (as root)
#   --deauth        Run: pcdctl deauthorize-node --verbose --no-prompt (as root)
#   --all           Run check-pf9, fix-fstab, unmount, check-dirs, decommission, deauth (excludes --clean-dirs)
#   -h              Show this help
#
# Requires: sshpass (apt install sshpass / yum install sshpass)

set -euo pipefail

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
HOSTS_FILE=""
SSH_USER=""
SSH_PASS=""
DO_CHECK_PF9=false
DO_FIX_FSTAB=false
DO_UNMOUNT=false
DO_CHECK_DIRS=false
DO_CLEAN_DIRS=false
DO_DECOMMISSION=false
DO_DEAUTH=false

# --------------------------------------------------------------------------- #
# Usage
# --------------------------------------------------------------------------- #
usage() {
  sed -n '3,21p' "$0" | sed 's/^# //' | sed 's/^#//'
  exit 0
}

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
[[ $# -eq 0 ]] && usage

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f)           HOSTS_FILE="$2"; shift 2 ;;
    -u)           SSH_USER="$2";   shift 2 ;;
    -p)           SSH_PASS="$2";   shift 2 ;;
    --check-pf9)  DO_CHECK_PF9=true; shift ;;
    --fix-fstab)  DO_FIX_FSTAB=true;  shift ;;
    --unmount)     DO_UNMOUNT=true;     shift ;;
    --check-dirs)  DO_CHECK_DIRS=true;  shift ;;
    --clean-dirs)    DO_CLEAN_DIRS=true;    shift ;;
    --decommission)  DO_DECOMMISSION=true;  shift ;;
    --deauth)        DO_DEAUTH=true;        shift ;;
    --all)        DO_CHECK_PF9=true; DO_FIX_FSTAB=true; DO_UNMOUNT=true; DO_CHECK_DIRS=true; DO_DECOMMISSION=true; DO_DEAUTH=true; shift ;;
    -h|--help)    usage ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$HOSTS_FILE"   ]] && { echo "ERROR: -f <hosts_file> is required" >&2; exit 1; }
[[ -z "$SSH_USER"     ]] && { echo "ERROR: -u <user> is required" >&2; exit 1; }
[[ -z "$SSH_PASS"     ]] && { echo "ERROR: -p <password> is required" >&2; exit 1; }
[[ ! -f "$HOSTS_FILE" ]] && { echo "ERROR: hosts file not found: $HOSTS_FILE" >&2; exit 1; }

if ! $DO_CHECK_PF9 && ! $DO_FIX_FSTAB && ! $DO_UNMOUNT && ! $DO_CHECK_DIRS && ! $DO_CLEAN_DIRS && ! $DO_DECOMMISSION && ! $DO_DEAUTH; then
  echo "ERROR: specify at least one action (--check-pf9 | --fix-fstab | --deauth | --all)" >&2
  exit 1
fi

if ! command -v sshpass &>/dev/null; then
  echo "ERROR: sshpass not found — install it first (apt install sshpass / yum install sshpass)" >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# SSH helper — password auth + root escalation via sudo
#
# sudo -S reads its password from stdin; bash -c reads the script from its
# argument (not stdin). The script is base64-encoded to safely pass it as a
# single argument — this avoids the password leaking into bash as a command,
# which happens when both sudo and bash compete for the same stdin.
# --------------------------------------------------------------------------- #
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o PasswordAuthentication=yes"

ssh_run() {
  local host="$1"
  local script="$2"
  local encoded
  encoded=$(printf '%s' "$script" | base64 | tr -d '\n')
  # shellcheck disable=SC2086
  sshpass -p "$SSH_PASS" ssh $SSH_OPTS "${SSH_USER}@${host}" \
    "sudo -S bash -c 'echo ${encoded} | base64 -d | bash'" <<< "$SSH_PASS"
}

# --------------------------------------------------------------------------- #
# Step 1 — Check installed pf9 packages
# --------------------------------------------------------------------------- #
check_pf9_packages() {
  local host="$1"
  echo "==> [${host}] PF9 packages"
  ssh_run "$host" 'dpkg -l | grep -i pf9 || echo "  (none found)"'
}

# --------------------------------------------------------------------------- #
# Step 2 — Comment out fstab entries for opt/data/instances and
#           var/lib/glance/images; leave all other entries intact
# --------------------------------------------------------------------------- #
fix_fstab() {
  local host="$1"
  echo "==> [${host}] /etc/fstab"

  # shellcheck disable=SC2016  # ${pattern} expands on the remote host, not locally
  ssh_run "$host" '
    fstab=/etc/fstab
    targets=("opt/data/instances" "var/lib/glance/images")
    changed=false

    for pattern in "${targets[@]}"; do
      match=$(grep -P "^[^#].*${pattern}" "$fstab" || true)
      if [[ -n "$match" ]]; then
        sed -i.bak -E "s|^([^#].*${pattern}.*)|#\1|" "$fstab"
        printf "  [COMMENTED] %s\n" "$match"
        changed=true
      else
        printf "  [SKIP]      no active entry matching: %s\n" "$pattern"
      fi
    done

    if $changed; then
      printf "\n  /etc/fstab (current state):\n"
      printf "  %s\n" "$(printf -- '-%.0s' {1..60})"
      while IFS= read -r line; do
        printf "  %s\n" "$line"
      done < "$fstab"
      printf "  %s\n" "$(printf -- '-%.0s' {1..60})"
    else
      printf "  no changes needed\n"
    fi
  '
}

# --------------------------------------------------------------------------- #
# Step 3 — Unmount target paths if currently mounted
# --------------------------------------------------------------------------- #
unmount_paths() {
  local host="$1"
  echo "==> [${host}] Unmounting data paths"

  # shellcheck disable=SC2016  # ${path} expands on the remote host, not locally
  ssh_run "$host" '
    targets=("/opt/data/instances" "/var/lib/glance/images")

    for path in "${targets[@]}"; do
      if mountpoint -q "$path" 2>/dev/null; then
        printf "  [UNMOUNT] %s is mounted — running umount -vvv\n" "$path"
        umount -vvv "$path"
      else
        printf "  [SKIP]    %s is not mounted\n" "$path"
      fi
    done
  '
}

# --------------------------------------------------------------------------- #
# Step 4 — Report presence of known PF9 artifact paths
# --------------------------------------------------------------------------- #
check_pf9_dirs() {
  local host="$1"
  echo "==> [${host}] PF9 artifact paths"

  # shellcheck disable=SC2016,SC2046
  ssh_run "$host" '
    paths=(
      /etc/pf9
      /var/log/pf9
      /var/spool/mail/pf9
      /root/pf9
      /var/opt/imagelibrary/data/glance
      /opt/data/instances
      /opt/pf9/data/state/compute_id
      /var/opt/pf9/neutron/metadata_proxy
      /opt/pf9/data/locks
      /opt/pf9/python
      /etc/pf9_environment
    )
    found=0
    total=${#paths[@]}
    for path in "${paths[@]}"; do
      if [ -e "$path" ]; then
        type="file"; [ -d "$path" ] && type="dir"
        printf "  \033[1;33m[FOUND]\033[0m   %-48s (%s)\n" "$path" "$type"
        (( found++ )) || true
      else
        printf "  [ABSENT]  %s\n" "$path"
      fi
    done
    printf "\n  %d of %d paths present\n" "$found" "$total"
  '
}

# --------------------------------------------------------------------------- #
# Step 5 — Delete known PF9 artifact paths (DESTRUCTIVE — explicit flag only)
# --------------------------------------------------------------------------- #
clean_pf9_dirs() {
  local host="$1"
  echo "==> [${host}] Removing PF9 artifact paths"

  # shellcheck disable=SC2016
  ssh_run "$host" '
    paths=(
      /etc/pf9
      /var/log/pf9
      /var/spool/mail/pf9
      /root/pf9
      /var/opt/imagelibrary/data/glance
      /opt/data/instances
      /opt/pf9/data/state/compute_id
      /var/opt/pf9/neutron/metadata_proxy
      /opt/pf9/data/locks
      /opt/pf9/python
      /etc/pf9_environment
    )
    for path in "${paths[@]}"; do
      if [ -e "$path" ]; then
        rm -rf "$path"
        printf "  \033[1;31m[DELETED]\033[0m %s\n" "$path"
      else
        printf "  [SKIP]    %s (not present)\n" "$path"
      fi
    done
  '
}

# --------------------------------------------------------------------------- #
# Step 6 — Decommission the node via pcdctl (runs as root via sudo in ssh_run)
#
# Before running pcdctl, performs two remote pre-checks:
#   1. PF9 package count  (dpkg -l | grep -i pf9)
#   2. PF9 artifact path count  (same list as --check-dirs)
# If both return zero the node is already clean and decommission is skipped.
# --------------------------------------------------------------------------- #
decommission_node() {
  local host="$1"
  echo "==> [${host}] pcdctl decommission-node"

  local pkg_count dir_count
  pkg_count=$(ssh_run "$host" 'dpkg -l 2>/dev/null | grep -ic pf9 || true' | tr -d '[:space:]')
  # shellcheck disable=SC2016  # ${paths[@]}, ${path}, ${count} expand on the remote host
  dir_count=$(ssh_run  "$host" '
    paths=(
      /etc/pf9 /var/log/pf9 /var/spool/mail/pf9 /root/pf9
      /var/opt/imagelibrary/data/glance /opt/data/instances
      /opt/pf9/data/state/compute_id /var/opt/pf9/neutron/metadata_proxy
      /opt/pf9/data/locks /opt/pf9/python /etc/pf9_environment
    )
    count=0
    for path in "${paths[@]}"; do [ -e "$path" ] && (( count++ )) || true; done
    echo "$count"
  ' | tr -d '[:space:]')

  if [[ "$pkg_count" -eq 0 && "$dir_count" -eq 0 ]]; then
    echo "  [SKIP] host already decommissioned — no PF9 packages and no artifact paths found"
    return 0
  fi

  echo "  Pre-check: ${pkg_count} PF9 package(s), ${dir_count} artifact path(s) present — proceeding"
  ssh_run "$host" 'pcdctl decommission-node --verbose --no-prompt'
}

# --------------------------------------------------------------------------- #
# Step 7 — Deauthorize the node via pcdctl (runs as root via sudo in ssh_run)
# --------------------------------------------------------------------------- #
deauthorize_node() {
  local host="$1"
  echo "==> [${host}] pcdctl deauthorize-node"
  ssh_run "$host" 'pcdctl deauthorize-node --verbose --no-prompt'
}

# --------------------------------------------------------------------------- #
# Main — iterate over hosts
# --------------------------------------------------------------------------- #
while IFS= read -r host || [[ -n "$host" ]]; do
  [[ -z "$host" || "$host" =~ ^# ]] && continue

  printf '\n%s\n HOST: %s\n%s\n' \
    "============================================================" \
    "$host" \
    "============================================================"

  $DO_CHECK_PF9   && { check_pf9_packages "$host" || echo "  [WARN] check_pf9_packages failed on ${host}"; }
  $DO_FIX_FSTAB   && { fix_fstab         "$host" || echo "  [WARN] fix_fstab failed on ${host}"; }
  $DO_UNMOUNT     && { unmount_paths      "$host" || echo "  [WARN] unmount_paths failed on ${host}"; }
  $DO_CHECK_DIRS  && { check_pf9_dirs    "$host" || echo "  [WARN] check_pf9_dirs failed on ${host}"; }
  $DO_CLEAN_DIRS    && { clean_pf9_dirs    "$host" || echo "  [WARN] clean_pf9_dirs failed on ${host}"; }
  $DO_DECOMMISSION  && { decommission_node "$host" || echo "  [WARN] decommission_node failed on ${host}"; }
  $DO_DEAUTH        && { deauthorize_node  "$host" || echo "  [WARN] deauthorize_node failed on ${host}"; }

done < "$HOSTS_FILE"

printf '\nDone.\n'
