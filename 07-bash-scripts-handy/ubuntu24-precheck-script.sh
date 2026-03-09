#!/usr/bin/env bash
# Ubuntu 24.04 pre-req script

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <ip-to-check-in-etc-hosts> [ip2] [ip3]..."
    exit 1
fi

CHECK_IP=("$@")

health_check() {
    local section="$1"
    shift
    echo "=== $section ==="
    "$@"
    echo
}

check_sudoers() {
    local PWLESS_USERS=()
    local SUDOERS_DIR="/etc/sudoers.d"
    
    # Safe main sudoers check
    if [[ -r /etc/sudoers ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" =~ ^([^#][^[:space:]]+)[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL$ ]]; then
                PWLESS_USERS+=("${BASH_REMATCH[1]} (sudoers)")
            fi
        done < <(grep -hE '^[^#][^[:space:]]+[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL' /etc/sudoers || true)
    fi
    
    # Safe sudoers.d scan
    if [[ -d "$SUDOERS_DIR" ]]; then
        for f in "$SUDOERS_DIR"/*; do
            [[ -r "$f" ]] || continue
            filename=$(basename "$f")
            if grep -q "^${filename} ALL=(ALL) NOPASSWD: ALL" "$f" 2>/dev/null || true; then
                PWLESS_USERS+=("$filename ($f)")
            fi
            while IFS= read -r line || [[ -n "$line" ]]; do
                if [[ "$line" =~ ^([^#][^[:space:]]+)[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL$ ]]; then
                    PWLESS_USERS+=("${BASH_REMATCH[1]} ($f)")
                fi
            done < <(grep -hE '^[^#][^[:space:]]+[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL' "$f" 2>/dev/null || true)
        done
    fi
    
    if [[ ${#PWLESS_USERS[@]} -gt 0 ]]; then
        echo "✅ Users (${#PWLESS_USERS[@]}):"
        printf '   %s\n' "${PWLESS_USERS[@]}"
    else
        echo "❌ None"
    fi
}

check_bond() {
    local BOND_IFACE=$(ip -d link show type bond 2>/dev/null | grep -o 'bond[0-9]*' | head -1 || true)
    if [[ -n "$BOND_IFACE" && -r "/proc/net/bonding/$BOND_IFACE" ]]; then
        local BOND_MODE=$(grep "^Bonding Mode:" "/proc/net/bonding/$BOND_IFACE" 2>/dev/null | awk '{print $3}' || true)
        if [[ "$BOND_MODE" == "802.3ad" ]]; then
            local BOND_IP=$(ip -4 addr show dev "$BOND_IFACE" scope global 2>/dev/null | awk '/inet / {print $2}' || true)
            echo "✅ Mode4: $BOND_IFACE (IP: $BOND_IP)"
            return
        fi
        echo "⚠️  $BOND_IFACE (mode: $BOND_MODE)"
    else
        echo "❌ No bond4"
    fi
}

check_ntp() {
    if command -v timedatectl >/dev/null 2>&1; then
        local NTP_STATUS=$(timedatectl 2>/dev/null | grep "NTP" | awk '{print $3}' || true)
        local SYNC_STATUS=$(timedatectl 2>/dev/null | grep "System clock synchronized:" |awk '{print $4}'|| true)
        [[ "$NTP_STATUS" == "active" && "$SYNC_STATUS" == "yes" ]] && echo "✅ Synced" || echo "❌ $NTP_STATUS/$SYNC_STATUS"
    else
        echo "❌ No timedatectl"
    fi
}

check_packages() {
    local PACKAGES="lsscsi sg3-utils multipath-tools scsitools open-iscsi nfs-common"
    local MISSING=()
    for pkg in $PACKAGES; do
        dpkg -l 2>/dev/null | grep -q "^ii.*$pkg " || MISSING+=("$pkg")
    done
    [[ ${#MISSING[@]} -eq 0 ]] && echo "✅ All OK" || echo "❌ Missing: ${MISSING[*]}"
}

check_services() {
    for svc in iscsid multipathd; do
        systemctl is-active --quiet "$svc" 2>/dev/null && echo "✅ $svc" || echo "❌ $svc"
    done
}

check_iscsi_initiator() {
    if [[ -r /etc/iscsi/initiatorname.iscsi ]]; then
        local INITIATOR=$(grep -v '^#' /etc/iscsi/initiatorname.iscsi 2>/dev/null | grep 'InitiatorName=' | cut -d'=' -f2- || true)
        [[ -n "$INITIATOR" ]] && echo "✅ $INITIATOR" || echo "❌ Empty"
    else
        echo "❌ initiatorname file not configured or missing"
    fi
}

check_multipath_blacklist() {
    if [[ -r /etc/multipath.conf ]]; then
        local BLACKLIST=$(awk '/^\[blacklist\]/,/^\[/ {if (/^(devnode|wwid|device)/) print}' /etc/multipath.conf 2>/dev/null)
        [[ -n "$BLACKLIST" ]] && { echo "✅"; echo "$BLACKLIST"; } || echo "⚠️  None"
    else
        echo "❌ multipath blacklist of local drive Missing"
        echo " /lib/udev/scsi_id -gud </dev/diskname> command to get the wwid for local drives to blacklist"
    fi
}

check_lvm_filters() {
    local LVM_CONF="/etc/lvm/lvm.conf"
    if [[ -r "$LVM_CONF" ]]; then
        local FILTER=$(awk '/filter/ {print; getline; print; getline; print}' "$LVM_CONF" 2>/dev/null | grep -i filter || true)
        local GLOBAL_FILTER=$(awk '/global_filter/ {print; getline; print; getline; print}' "$LVM_CONF" 2>/dev/null | grep -i global_filter || true)
        [[ -n "$FILTER" ]] && echo "✅ Filter: $FILTER"
        [[ -n "$GLOBAL_FILTER" ]] && echo "✅ Global: $GLOBAL_FILTER"
        [[ -z "$FILTER" && -z "$GLOBAL_FILTER" ]] && echo "❌ None"
    else
        echo "❌ no filter set in lvm.conf"
    fi
}

check_hosts() {
    if [[ ! -r /etc/hosts ]]; then
        echo "❌ /etc/hosts not readable"
        return 1
    fi
    for ip in "${CHECK_IP[@]}"; do
        echo "Checking IP: $ip"

        local ENTRY
        ENTRY=$(grep -E "^[[:space:]]*$ip([[:space:]]+|$)" /etc/hosts || true)

        if [[ -n "$ENTRY" ]]; then
            echo "✅ found entries for $ip"
            echo "$ENTRY"
        else
            echo "❌ missing entries for $ip"
            echo "$ip: Not found"
        fi
        echo
    done
}

# RUN ALL CHECKS SAFELY
health_check "1. PASSWORDLESS SUDO" check_sudoers
health_check "2. BOND MODE4" check_bond
health_check "3. NTP" check_ntp
health_check "4. PACKAGES" check_packages
health_check "5. SERVICES" check_services
health_check "6. ISCSI INITIATOR" check_iscsi_initiator
health_check "7. MP BLACKLIST" check_multipath_blacklist
health_check "8. LVM FILTERS" check_lvm_filters
health_check "9. /ETC/HOSTS" check_hosts

echo "✅ ALL CHECKS COMPLETE!"