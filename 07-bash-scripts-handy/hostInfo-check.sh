#!/usr/bin/env bash

set -euo pipefail

RUN_VIRSH=0
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--virsh" ]]; then
        RUN_VIRSH=1
    else
        ARGS+=("$arg")
    fi
done

if [[ ${#ARGS[@]} -eq 0 ]]; then
    echo "Usage: $0 [--virsh] <ip-to-check-in-etc-hosts> [ip2] [ip3]..."
    exit 1
fi

CHECK_IP=("${ARGS[@]}")

# ── Color definitions ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

OK()   { printf "  ${GREEN}[ OK ]${NC}  %s\n" "$*"; }
FAIL() { printf "  ${RED}[ FAIL ]${NC}  %s\n" "$*"; }
WARN() { printf "  ${YELLOW}[ WARN ]${NC}  %s\n" "$*"; }
INFO() { printf "  ${DIM}         ${NC}  %s\n" "$*"; }

health_check() {
    local section="$1"
    shift
    printf "\n${CYAN}${BOLD}━━━  %-40s━━━${NC}\n" "$section "
    "$@" || true
}

# ── Checks ─────────────────────────────────────────────────────────────────────

check_sudoers() {
    local PWLESS_USERS=()
    local SUDOERS_DIR="/etc/sudoers.d"

    if [[ -r /etc/sudoers ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" =~ ^([^#][^[:space:]]+)[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL$ ]]; then
                PWLESS_USERS+=("${BASH_REMATCH[1]} (sudoers)")
            fi
        done < <(grep -hE '^[^#][^[:space:]]+[[:space:]]+ALL=\(ALL\)[[:space:]]+NOPASSWD:[[:space:]]+ALL' /etc/sudoers || true)
    fi

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
        OK "Users with passwordless sudo (${#PWLESS_USERS[@]}):"
        printf '             %s\n' "${PWLESS_USERS[@]}"
    else
        FAIL "No passwordless sudo users found"
    fi
}

check_bond() {
    local BOND_IFACE
    BOND_IFACE=$(ip -d link show type bond 2>/dev/null | grep -o 'bond[0-9]*' | head -1 || true)
    if [[ -n "$BOND_IFACE" && -r "/proc/net/bonding/$BOND_IFACE" ]]; then
        local BOND_MODE
        BOND_MODE=$(grep "^Bonding Mode:" "/proc/net/bonding/$BOND_IFACE" 2>/dev/null | awk '{print $4}' || true)
        if [[ "$BOND_MODE" == "802.3ad" ]]; then
            local BOND_IP
            BOND_IP=$(ip -4 addr show dev "$BOND_IFACE" scope global 2>/dev/null | awk '/inet / {print $2}' || true)
            OK "Mode4 (802.3ad): $BOND_IFACE  IP: $BOND_IP"
            return
        fi
        WARN "$BOND_IFACE is active but mode is '$BOND_MODE' (expected 802.3ad)"
    else
        FAIL "No bond interface in mode 4 found"
    fi
}

check_ntp() {
    if command -v timedatectl >/dev/null 2>&1; then
        local NTP_STATUS SYNC_STATUS
        NTP_STATUS=$(timedatectl 2>/dev/null | grep "NTP" | awk '{print $3}' || true)
        SYNC_STATUS=$(timedatectl 2>/dev/null | grep "System clock synchronized:" | awk '{print $4}' || true)
        if [[ "$NTP_STATUS" == "active" && "$SYNC_STATUS" == "yes" ]]; then
            OK "NTP active and clock synchronized"
        else
            FAIL "NTP status: ${NTP_STATUS:-unknown}  |  Synchronized: ${SYNC_STATUS:-unknown}"
        fi
    else
        FAIL "timedatectl not available"
    fi
}

check_packages() {
    local PACKAGES="lsscsi sg3-utils multipath-tools scsitools open-iscsi nfs-common"
    local MISSING=()
    for pkg in $PACKAGES; do
        dpkg -l "$pkg" 2>/dev/null | grep -q "^ii" || MISSING+=("$pkg")
    done
    if [[ ${#MISSING[@]} -eq 0 ]]; then
        OK "All required packages installed"
    else
        FAIL "Missing packages: ${MISSING[*]}"
    fi
}

check_services() {
    for svc in iscsid multipathd; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            OK "$svc is running"
        else
            FAIL "$svc is not running"
        fi
    done
}

check_iscsi_initiator() {
    if [[ -r /etc/iscsi/initiatorname.iscsi ]]; then
        local INITIATOR
        INITIATOR=$(grep -v '^#' /etc/iscsi/initiatorname.iscsi 2>/dev/null | grep 'InitiatorName=' | cut -d'=' -f2- || true)
        if [[ -n "$INITIATOR" ]]; then
            OK "$INITIATOR"
        else
            FAIL "InitiatorName is empty"
        fi
    else
        FAIL "initiatorname.iscsi not found or not readable"
    fi

    if systemctl is-active --quiet iscsid 2>/dev/null; then
        OK "iscsid: running"
        local sessions
        sessions=$(iscsiadm -m session 2>/dev/null || true)
        if [[ -n "$sessions" ]]; then
            INFO "iSCSI sessions:"
            while IFS= read -r line; do
                INFO "  $line"
            done <<< "$sessions"
        else
            WARN "No active iSCSI sessions"
        fi
    else
        WARN "iscsid: not running"
    fi
}

check_multipath_blacklist() {
    if [[ -r /etc/multipath.conf ]]; then
        local BLACKLIST
        BLACKLIST=$(awk '/^\[blacklist\]/,/^\[/ {if (/^(devnode|wwid|device)/) print}' /etc/multipath.conf 2>/dev/null)
        if [[ -n "$BLACKLIST" ]]; then
            OK "Blacklist entries found:"
            INFO "$BLACKLIST"
        else
            WARN "No blacklist entries in multipath.conf"
        fi
    else
        FAIL "multipath.conf not found — local drive blacklist missing"
        INFO "Run: /lib/udev/scsi_id -gud </dev/diskname>  to get WWID for local drives"
    fi
}

check_lvm_filters() {
    local LVM_CONF="/etc/lvm/lvm.conf"
    if [[ -r "$LVM_CONF" ]]; then
        local FILTER GLOBAL_FILTER
        FILTER=$(grep -E '^\s*filter\s*=' "$LVM_CONF" 2>/dev/null || true)
        GLOBAL_FILTER=$(grep -E '^\s*global_filter\s*=' "$LVM_CONF" 2>/dev/null || true)
        [[ -n "$FILTER" ]]        && OK "filter:        $FILTER"
        [[ -n "$GLOBAL_FILTER" ]] && OK "global_filter: $GLOBAL_FILTER"
        [[ -z "$FILTER" && -z "$GLOBAL_FILTER" ]] && FAIL "No filter or global_filter set in lvm.conf"
    else
        FAIL "lvm.conf not found"
    fi
}

check_hosts() {
    if [[ ! -r /etc/hosts ]]; then
        FAIL "/etc/hosts not readable"
        return 1
    fi
    for ip in "${CHECK_IP[@]}"; do
        local ENTRY
        ENTRY=$(grep -E "^[[:space:]]*$ip([[:space:]]+|$)" /etc/hosts || true)
        if [[ -n "$ENTRY" ]]; then
            OK "$ip  found in /etc/hosts"
            INFO "$ENTRY"
        else
            FAIL "$ip  not found in /etc/hosts"
        fi
    done
}

check_pf9_services() {
    local services=(pf9-ostackhost.service pf9-cindervolume-base.service pf9-glance-api.service)
    for svc in "${services[@]}"; do
        local unit="${svc}"
        if systemctl is-active --quiet "$unit" 2>/dev/null; then
            OK "$svc: running"
        elif systemctl list-units --type=service --all 2>/dev/null | grep -q "${unit}"; then
            FAIL "$svc: not running / failed"
        else
            WARN "$svc: not installed"
        fi
    done
}

check_ovs_bridges() {
    if ! command -v ovs-vsctl >/dev/null 2>&1; then
        FAIL "ovs-vsctl not installed"
        return
    fi

    local bridges
    bridges=$(ovs-vsctl list-br 2>/dev/null || true)
    if [[ -z "$bridges" ]]; then
        FAIL "No OVS bridges configured"
        return
    fi

    while read -r br; do
        [[ -z "$br" ]] && continue
        local ip
        ip=$(ip -4 addr show dev "$br" 2>/dev/null | awk '/inet / {print $2; exit}' || true)
        if [[ -n "$ip" ]]; then
            OK "Bridge: $br  IP: $ip"
        else
            WARN "Bridge: $br  (no IPv4 address)"
        fi

        local ports
        ports=$(ovs-vsctl list-ports "$br" 2>/dev/null || true)

        if [[ "$br" == "br-int" ]]; then
            if [[ -n "$ports" ]]; then
                INFO "Ports: listing all ports on br-int (including virtual):"
                echo "$ports"
            else
                INFO "Ports: none"
            fi
        else
            local physical_ports=()
            while read -r p; do
                [[ -z "$p" ]] && continue
                local iface_type
                iface_type=$(ovs-vsctl get interface "$p" type 2>/dev/null || true)
                [[ "$iface_type" == "patch" || "$iface_type" == "internal" ]] && continue
                if [[ "$p" =~ ^(ens|eth|bond|vlan|em|enp|eno)[0-9] ]]; then
                    physical_ports+=("$p")
                fi
            done <<< "$ports"
            if [[ ${#physical_ports[@]} -gt 0 ]]; then
                INFO "Physical ports: ${physical_ports[*]}"
            else
                INFO "Physical ports: none"
            fi
        fi
    done <<< "$bridges"
}

find_multipath_for_device() {
    local dev="$1"
    local real
    real=$(readlink -f "$dev" 2>/dev/null || echo "$dev")

    if [[ "$real" == /dev/mapper/* ]]; then
        echo "$real"
        return
    fi

    local mpath
    mpath=$(multipath -ll 2>/dev/null | grep -B1 -F "$real" | head -n1 | awk '{print $1}' || true)
    if [[ -z "$mpath" ]]; then
        local base
        base=$(basename "$real")
        mpath=$(multipath -ll 2>/dev/null | grep -B1 -F "$base" | head -n1 | awk '{print $1}' || true)
    fi

    if [[ -n "$mpath" ]]; then
        echo "/dev/mapper/$mpath"
    else
        echo "$real"
    fi
}

check_virsh_vms() {
    if ! command -v virsh >/dev/null 2>&1; then
        FAIL "virsh not installed"
        return
    fi

    local vms
    vms=$(virsh list --name --state-running 2>/dev/null || true)
    if [[ -z "$vms" ]]; then
        WARN "No running VMs"
        return
    fi

    while read -r vm; do
        [[ -z "$vm" ]] && continue
        OK "VM: $vm"

        local domblk
        domblk=$(virsh domblklist --details "$vm" 2>/dev/null || true)

        if [[ -z "$domblk" ]]; then
            WARN "No block devices found for $vm"
            continue
        fi

        INFO "Block device list:"
        while IFS= read -r line; do
            INFO "  $line"
        done <<< "$domblk"

        local dms=()
        mapfile -t dms < <(awk '{print $4}' <<< "$domblk" | grep -oE 'dm-[0-9]+' | sort -u)

        if ((${#dms[@]} == 0)); then
            WARN "No dm-* devices found for $vm"
            continue
        fi

        INFO "Multipath mapping:"
        for dm in "${dms[@]}"; do
            local mpath_line mpath_name
            mpath_line=$(multipath -ll 2>/dev/null | grep -E "\\b${dm}\\b" | head -1 || true)
            if [[ -n "$mpath_line" ]]; then
                mpath_name=$(awk '{print $1}' <<< "$mpath_line")
                INFO "  $dm  ->  $mpath_name  (/dev/mapper/$mpath_name)"
            else
                WARN "  $dm  ->  not found in multipath"
            fi
        done
    done <<< "$vms"
}

# ── Run all checks ─────────────────────────────────────────────────────────────

#health_check "1.  PASSWORDLESS SUDO"  check_sudoers
health_check "1.  CHECK BOND MODE"    check_bond
health_check "2.  NTP"                check_ntp
health_check "3.  PACKAGES"           check_packages
health_check "4.  SERVICES"           check_services
health_check "5.  ISCSI INITIATOR"    check_iscsi_initiator
health_check "6.  MULTIPATH BLACKLIST" check_multipath_blacklist
health_check "7.  LVM FILTERS"        check_lvm_filters
health_check "8.  /ETC/HOSTS"         check_hosts
health_check "9.  PF9 SERVICES"       check_pf9_services
health_check "10. OVS BRIDGES"        check_ovs_bridges
#if ((RUN_VIRSH)); then
#    health_check "11. VIRSH VMS"      check_virsh_vms
#fi
