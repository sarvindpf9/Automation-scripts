#!/usr/bin/env bash

set -euo pipefail

VIRSH_UUID=""
CHECK_SUDOERS=false
OUTPUT_FILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --virsh)       ;;  # kept for backwards compat; --uuid implies virsh
        --uuid)        shift; VIRSH_UUID="$1" ;;
        check-sudoers) CHECK_SUDOERS=true ;;
        --log)         OUTPUT_FILE="hostcheck-$(hostname -s)-$(date '+%Y%m%d_%H%M%S').log" ;;
        --output)      shift; OUTPUT_FILE="$1" ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--uuid <vm-uuid>] [check-sudoers] [--log | --output <file>]"
            echo "  --uuid <uuid>     also check virsh VM disk/multipath"
            echo "  check-sudoers     also run passwordless sudo check"
            echo "  --log             write output to hostcheck-<hostname>-<timestamp>.log"
            echo "  --output <file>   write output to the specified file"
            exit 1
            ;;
    esac
    shift
done

if [[ -n "$OUTPUT_FILE" ]]; then
    printf "=== hostInfo-check | host: %s | %s ===\n\n" \
        "$(hostname -s)" "$(date '+%Y-%m-%d %H:%M:%S')" > "$OUTPUT_FILE"
    exec > >(tee >(sed 's/\x1b\[[0-9;]*m//g' >> "$OUTPUT_FILE")) 2>&1
fi

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
    printf "\n${CYAN}${BOLD}━━━  %-10s━━━${NC}\n" "$section "
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
    local bond_ifaces
    mapfile -t bond_ifaces < <(ip -o link show type bond 2>/dev/null | awk -F': ' '{print $2}' || true)

    if [[ ${#bond_ifaces[@]} -eq 0 ]]; then
        FAIL "No bond interfaces found"
        return
    fi

    for BOND_IFACE in "${bond_ifaces[@]}"; do
        local BOND_MODE BOND_IP
        BOND_MODE=$(awk -F': ' '/^Bonding Mode:/{print $2}' "/proc/net/bonding/$BOND_IFACE" 2>/dev/null || true)
        BOND_IP=$(ip -4 addr show dev "$BOND_IFACE" scope global 2>/dev/null | awk '/inet / {print $2}' || true)

        if [[ "$BOND_MODE" == *"802.3ad"* ]]; then
            OK "$BOND_IFACE  mode: $BOND_MODE  IP: ${BOND_IP:-none}"
        else
            WARN "$BOND_IFACE  mode: ${BOND_MODE:-unknown}  IP: ${BOND_IP:-none}  (expected 802.3ad)"
        fi
    done
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
    for pkg in $PACKAGES; do
        if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            OK "$pkg"
        else
            FAIL "$pkg  (not installed)"
        fi
    done
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

check_iscsid_conf() {
    if ! command -v iscsid >/dev/null 2>&1; then
        WARN "iscsid not installed — skipping iscsid.conf check"
        return
    fi

    local conf=/etc/iscsi/iscsid.conf
    if [[ ! -r "$conf" ]]; then
        FAIL "$conf not found or not readable"
        return
    fi

    local -A expected=(
        ["node.session.timeo.replacement_timeout"]="15"
        ["node.conn[0].timeo.login_timeout"]="5"
        ["node.conn[0].timeo.logout_timeout"]="5"
        ["node.session.err_timeo.abort_timeout"]="10"
        ["node.session.err_timeo.lu_reset_timeout"]="20"
    )

    for key in \
        "node.session.timeo.replacement_timeout" \
        "node.conn[0].timeo.login_timeout" \
        "node.conn[0].timeo.logout_timeout" \
        "node.session.err_timeo.abort_timeout" \
        "node.session.err_timeo.lu_reset_timeout"; do

        local want="${expected[$key]}" got
        # FS splits on whitespace-padded '='; key is compared literally (safe with [0] and dots)
        got=$(awk -F'[[:space:]]*=[[:space:]]*' -v k="$key" '
            /^[[:space:]]*#/ { next }
            NF >= 2 {
                kf = $1; gsub(/^[[:space:]]+|[[:space:]]+$/, "", kf)
                if (kf == k) { print $2; exit }
            }
        ' "$conf")

        if   [[ "$got" == "$want" ]]; then OK   "$key = $got"
        elif [[ -n "$got" ]];         then WARN "$key = $got  (expected: $want)"
        else                               FAIL "$key not set  (expected: $want)"
        fi
    done
}

check_multipath_blacklist() {
    if [[ ! -r /etc/multipath.conf ]]; then
        FAIL "multipath.conf not found — local drive blacklist missing"
        INFO "Run: /lib/udev/scsi_id -gud </dev/diskname>  to get WWID for local drives"
        return
    fi

    local conf=/etc/multipath.conf

    # ── defaults section ──────────────────────────────────────────────────────
    local defaults_block
    defaults_block=$(awk '/^[[:space:]]*defaults[[:space:]]*\{/{f=1;next} f&&/^[[:space:]]*\}/{f=0;next} f{print}' "$conf")

    if [[ -z "$defaults_block" ]]; then
        FAIL "defaults{} section missing"
    else
        local -A defaults_want=(
            [find_multipaths]="yes"
            [no_path_retry]="12"
            [polling_interval]="5"
            [user_friendly_names]="no"
        )
        for key in find_multipaths no_path_retry polling_interval user_friendly_names; do
            local want="${defaults_want[$key]}" got
            got=$(printf '%s\n' "$defaults_block" | awk -v k="$key" '$1==k{print $2; exit}')
            if   [[ "$got" == "$want" ]]; then OK   "defaults: $key = $got"
            elif [[ -n "$got" ]];         then WARN "defaults: $key = $got  (expected: $want)"
            else                               FAIL "defaults: $key missing  (expected: $want)"
            fi
        done
    fi

    # ── blacklist section ──────────────────────────────────────────────────────
    local BLACKLIST
    BLACKLIST=$(awk '/^[[:space:]]*blacklist[[:space:]]*\{/,/^[[:space:]]*\}/ {if (/devnode|wwid|device/) print}' "$conf")
    if [[ -n "$BLACKLIST" ]]; then
        OK "blacklist: entries found:"
        while IFS= read -r line; do INFO "  $line"; done <<< "$BLACKLIST"
    else
        WARN "blacklist: no wwid/devnode entries"
    fi

    # ── devices / NETAPP device block ─────────────────────────────────────────
    local netapp_block
    netapp_block=$(awk '
        /^[[:space:]]*devices[[:space:]]*\{/ { in_d=1; depth=1; next }
        in_d {
            if (/\{/) { depth++; if (depth==2) { buf=""; in_dev=1 } }
            if (/\}/) {
                depth--
                if (depth==1 && in_dev) {
                    if (buf ~ /vendor[[:space:]]+"?NETAPP"?/) print buf
                    in_dev=0
                }
                if (depth==0) in_d=0
            }
            if (in_dev && !/[{}]/) buf = buf "\n" $0
        }
    ' "$conf")

    if [[ -z "$netapp_block" ]]; then
        WARN "devices: no NETAPP device block found."
    else
        OK "devices: NETAPP device block found"

        # single-word value params
        local -A sv_want=(
            [path_grouping_policy]="group_by_prio"
            [prio]="alua"
            [failback]="immediate"
            [fast_io_fail_tmo]="5"
            [dev_loss_tmo]="30"
        )
        for key in path_grouping_policy prio failback fast_io_fail_tmo dev_loss_tmo; do
            local want="${sv_want[$key]}" got
            got=$(printf '%s\n' "$netapp_block" | awk -v k="$key" '$1==k{print $2; exit}')
            if   [[ "$got" == "$want" ]]; then OK   "devices.device: $key = $got"
            elif [[ -n "$got" ]];         then WARN "devices.device: $key = $got  (expected: $want)"
            else                               FAIL "devices.device: $key missing  (expected: $want)"
            fi
        done

        # quoted / multi-word value params
        for kv in "product:LUN.*" "path_selector:service-time 0" "features:0" "hardware_handler:1 alua"; do
            local key="${kv%%:*}" want="${kv#*:}" got
            got=$(printf '%s\n' "$netapp_block" | awk -v k="$key" \
                '$1==k{for(i=2;i<=NF;i++) printf "%s%s",$i,(i<NF?" ":""); print ""; exit}' | tr -d '"')
            if   [[ "$got" == "$want" ]]; then OK   "devices.device: $key = $got"
            elif [[ -n "$got" ]];         then WARN "devices.device: $key = $got  (expected: $want)"
            else                               FAIL "devices.device: $key missing  (expected: $want)"
            fi
        done
    fi

    INFO ""
    INFO "── /etc/multipath.conf ──"
    while IFS= read -r line; do INFO "$line"; done < "$conf"
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
        return
    fi
    printf '  %b[ NOTE ]%b  Review and Ensure the SVM host IP mapping is set for the SVM FQDN to be resolvable\n' "$RED" "$NC"
    INFO ""
    while IFS= read -r line; do INFO "$line"; done < /etc/hosts
}

check_pf9_services() {
    local services=(pf9-ostackhost.service pf9-cindervolume-base.service pf9-glance-api.service pf9-comms.service pf9-ha-slave.service pf9-hostagent.service pf9-libvirt-exporter.service pf9-neutron-ovn-metadata-agent.service pf9-node-exporter.service pf9-novncproxy.service pf9-prometheus.service pf9-remote-write.service pf9-sidekick.service)
    local ostackhost_running=false cindervolume_running=false ha_slave_present=true
    for svc in "${services[@]}"; do
        local unit="${svc}"
        if systemctl is-active --quiet "$unit" 2>/dev/null; then
            OK "$svc: running"
            [[ "$svc" == "pf9-ostackhost.service" ]]          && ostackhost_running=true
            [[ "$svc" == "pf9-cindervolume-base.service" ]]   && cindervolume_running=true
        elif systemctl list-units --type=service --all 2>/dev/null | grep -q "${unit}"; then
            FAIL "$svc: not running / failed"
            [[ "$svc" == "pf9-ha-slave.service" ]] && ha_slave_present=false
        else
            WARN "$svc: not installed"
            [[ "$svc" == "pf9-ha-slave.service" ]] && ha_slave_present=false
        fi
    done

    if [[ "$ha_slave_present" == false ]]; then
        INFO "pf9-ha-slave not present — pf9-remote-write.service:"
        if systemctl is-active --quiet pf9-remote-write.service 2>/dev/null; then
            OK "pf9-remote-write.service: running"
        elif systemctl list-units --type=service --all 2>/dev/null | grep -q "pf9-remote-write.service"; then
            FAIL "pf9-remote-write.service: not running / failed"
        else
            WARN "pf9-remote-write.service: not installed"
        fi
    fi

    if [[ "$ostackhost_running" == true ]]; then
        local nova_conf="/opt/pf9/etc/nova/conf.d/nova_override.conf"
        printf "\n  %b[ nova_override.conf ]%b\n" "$CYAN" "$NC"
        if [[ -r "$nova_conf" ]]; then
            local vol_mp iscsi_mp
            vol_mp=$(grep -E '^\s*volume_use_multipath\s*=' "$nova_conf" 2>/dev/null || true)
            if [[ -n "$vol_mp" ]]; then
                OK "volume_use_multipath: $vol_mp"
            else
                WARN "volume_use_multipath not set in nova_override.conf"
            fi
            iscsi_mp=$(grep -E '^\s*iscsi_use_multipath\s*=' "$nova_conf" 2>/dev/null || true)
            if [[ -n "$iscsi_mp" ]]; then
                OK "iscsi_use_multipath: $iscsi_mp"
            else
                WARN "iscsi_use_multipath not set in nova_override.conf"
            fi
            INFO ""
            INFO "── $nova_conf ──"
            while IFS= read -r line; do INFO "$line"; done < "$nova_conf"
        else
            WARN "nova_override.conf not found or not readable: $nova_conf"
        fi

        local xml_uuids virsh_names only_xml only_virsh xml_count virsh_count
        xml_uuids=$(find /etc/libvirt/qemu/ -maxdepth 1 -name '*.xml' -exec basename {} .xml \; 2>/dev/null | sort)
        virsh_names=$(virsh list --all --name 2>/dev/null | grep -v '^$' | sort)

        only_xml=$(comm -23 <(echo "$xml_uuids") <(echo "$virsh_names"))
        only_virsh=$(comm -13 <(echo "$xml_uuids") <(echo "$virsh_names"))

        [[ -n "$only_xml" ]]   && echo -e "=== XML only (no virsh entry) ===\n$only_xml"
        [[ -n "$only_virsh" ]] && echo -e "=== virsh only (no XML file) ===\n$only_virsh"

        xml_count=$(echo "$xml_uuids" | grep -c .)
        virsh_count=$(echo "$virsh_names" | grep -c .)
        echo -e "\n${CYAN}${BOLD}=== Totals VMs running on this hypervisor ===${NC}\nnum_vm_configs_local    $xml_count\ntotal_vms_virsh:        $virsh_count"
    fi

    if [[ "$cindervolume_running" == true ]]; then
        local cinder_conf="/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder.conf"
        printf "\n  %b[ cinder.conf ]%b\n" "$CYAN" "$NC"
        if [[ -r "$cinder_conf" ]]; then
            for param in reserved_percentage goodness_function; do
                local val
                val=$(grep -E "^\s*${param}\s*=" "$cinder_conf" 2>/dev/null || true)
                if [[ -n "$val" ]]; then
                    OK "$val"
                else
                    WARN "$param not set in cinder.conf"
                fi
            done
        else
            WARN "cinder.conf not found or not readable: $cinder_conf"
        fi
    fi
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
                while IFS= read -r port; do printf '             %s\n' "$port"; done <<< "$ports"
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

check_virsh_vms() {
    local uuid="$1"

    if ! command -v virsh >/dev/null 2>&1; then
        FAIL "virsh not installed"
        return
    fi

    local vm
    if [[ -n "$uuid" ]]; then
        vm=$(virsh domname "$uuid" 2>/dev/null || true)
        if [[ -z "$vm" ]]; then
            FAIL "No VM found with UUID: $uuid"
            return
        fi
    else
        FAIL "No UUID provided — use --uuid <vm-uuid>"
        return
    fi

    OK "VM: $vm  (UUID: $uuid)"

    local domblk
    domblk=$(virsh domblklist --details "$vm" 2>/dev/null || true)

    if [[ -z "$domblk" ]]; then
        WARN "No block devices found for $vm"
        return
    fi

    INFO "Block device list:"
    while IFS= read -r line; do
        INFO "  $line"
    done <<< "$domblk"

    local dms=()
    mapfile -t dms < <(awk '{print $4}' <<< "$domblk" | grep -oE 'dm-[0-9]+' | sort -u)

    if ((${#dms[@]} == 0)); then
        WARN "No dm-* devices found for $vm"
        return
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
}


[[ "$CHECK_SUDOERS" == true ]] && health_check "1.  PASSWORDLESS SUDO"   check_sudoers

health_check "2.  CHECK BOND MODE"     check_bond
health_check "3.  NTP"                 check_ntp
health_check "4.  PACKAGES"            check_packages
health_check "5.  SERVICES"            check_services
health_check "6.  ISCSI INITIATOR"     check_iscsi_initiator
health_check "7.  ISCSID CONF"         check_iscsid_conf
health_check "8.  MULTIPATH BLACKLIST"  check_multipath_blacklist
health_check "9.  LVM FILTERS"         check_lvm_filters
health_check "10. PF9 SERVICES"        check_pf9_services
health_check "11. OVS BRIDGES"         check_ovs_bridges

health_check "12. /ETC/HOSTS"              check_hosts

if [[ -n "$VIRSH_UUID" ]]; then
    health_check "13. VIRSH VMS"           check_virsh_vms "$VIRSH_UUID"
fi
