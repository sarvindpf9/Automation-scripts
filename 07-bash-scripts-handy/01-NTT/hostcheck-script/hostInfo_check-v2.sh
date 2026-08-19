#!/usr/bin/env bash

set -euo pipefail

VIRSH_UUID=""
CHECK_SUDOERS=false
CHECK_MPATH_ORPHAN=false
LIST_VM_MPATH=false
CHECK_GLANCE_MOUNT=false
GLANCE_MOUNT_DIR="/var/opt/imagelibrary/"
OUTPUT_FILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --virsh)            ;;  # kept for backwards compat; --uuid implies virsh
        --uuid)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                printf 'ERROR: --uuid requires a non-empty value\n' >&2
                exit 2
            fi
            shift
            VIRSH_UUID="$1"
            ;;
        check-sudoers)      CHECK_SUDOERS=true ;;
        check-mpath-orphan) CHECK_MPATH_ORPHAN=true ;;
        list-vm-mpath)      LIST_VM_MPATH=true ;;
        check-glance-mount)
            CHECK_GLANCE_MOUNT=true
            if [[ $# -gt 1 && "${2:-}" != -* && "${2:-}" != check-* && "${2:-}" != list-* ]]; then
                shift
                GLANCE_MOUNT_DIR="$1"
            fi
            ;;
        --log)              OUTPUT_FILE="hostcheck-$(hostname -s)-$(date '+%Y%m%d_%H%M%S').log" ;;
        --output)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                printf 'ERROR: --output requires a non-empty value\n' >&2
                exit 2
            fi
            shift
            OUTPUT_FILE="$1"
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--uuid <vm-uuid>] [check-sudoers] [check-mpath-orphan] [list-vm-mpath] [check-glance-mount [directory]] [--log | --output <file>]"
            echo "  --uuid <uuid>        also check virsh VM disk/multipath by UUID"
            echo "  check-sudoers        also run passwordless sudo check"
            echo "  check-mpath-orphan   check for orphaned/faulty multipath devices"
            echo "  list-vm-mpath        list per-VM DM disks and multipath path state"
            echo "  check-glance-mount [directory]"
            echo "                       check fstab mapping and pf9:pf9group ownership"
            echo "                       (default: /var/opt/imagelibrary/)"
            echo "  --log                write output to hostcheck-<hostname>-<timestamp>.log"
            echo "  --output <file>      write output to the specified file"
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

OS_ID=""
OS_VERSION_ID=""
OS_PRETTY_NAME=""
PACKAGE_FAMILY=""

detect_operating_system() {
    if [[ ! -r /etc/os-release ]]; then
        printf 'ERROR: /etc/os-release is missing or unreadable; cannot select a package backend.\n' >&2
        exit 2
    fi

    # /etc/os-release is the distribution-provided interface for OS identification.
    # shellcheck disable=SC1091
    source /etc/os-release
    OS_ID="${ID:-}"
    OS_VERSION_ID="${VERSION_ID:-}"
    OS_PRETTY_NAME="${PRETTY_NAME:-${OS_ID:-unknown} ${OS_VERSION_ID:-unknown}}"

    case "$OS_ID" in
        ubuntu)
            PACKAGE_FAMILY="deb"
            command -v dpkg-query >/dev/null 2>&1 || {
                printf 'ERROR: Ubuntu detected but dpkg-query is unavailable.\n' >&2
                exit 2
            }
            ;;
        rocky|rhel|almalinux)
            PACKAGE_FAMILY="rpm"
            command -v rpm >/dev/null 2>&1 || {
                printf 'ERROR: %s detected but rpm is unavailable.\n' "$OS_ID" >&2
                exit 2
            }
            ;;
        *)
            printf 'ERROR: unsupported operating system ID %q. Supported IDs: ubuntu, rocky, rhel, almalinux.\n' \
                "${OS_ID:-unset}" >&2
            exit 2
            ;;
    esac
}

package_is_installed() {
    local package_name="$1"

    case "$PACKAGE_FAMILY" in
        deb)
            [[ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$package_name" 2>/dev/null || true)" == "ii " ]]
            ;;
        rpm)
            rpm -q --quiet "$package_name" 2>/dev/null
            ;;
        *)
            return 2
            ;;
    esac
}

check_package_alternatives() {
    local requirement="$1"
    shift
    local package_name

    for package_name in "$@"; do
        if package_is_installed "$package_name"; then
            OK "$requirement  (package: $package_name)"
            return
        fi
    done

    FAIL "$requirement  (none installed: $*)"
}

check_command_provider() {
    local requirement="$1"
    local command_name="$2"
    local command_path provider=""

    command_path=$(command -v "$command_name" 2>/dev/null || true)
    if [[ -z "$command_path" ]]; then
        FAIL "$requirement  (command unavailable: $command_name)"
        return
    fi

    case "$PACKAGE_FAMILY" in
        deb) provider=$(dpkg-query -S "$command_path" 2>/dev/null | head -1 | cut -d: -f1 || true) ;;
        rpm) provider=$(rpm -qf --queryformat '%{NAME}' "$command_path" 2>/dev/null || true) ;;
    esac
    OK "$requirement  (command: $command_path${provider:+, package: $provider})"
}

service_load_state() {
    local unit="$1"
    systemctl show "$unit" --property=LoadState --value 2>/dev/null || true
}

detect_operating_system

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
            if [[ "$line" =~ ^([^#][^[:space:]]+)[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:[[:space:]]+ALL$ ]]; then
                PWLESS_USERS+=("${BASH_REMATCH[1]} (sudoers)")
            fi
        done < <(grep -hE '^[^#][^[:space:]]+[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:[[:space:]]+ALL' /etc/sudoers || true)
    fi

    if [[ -d "$SUDOERS_DIR" ]]; then
        for f in "$SUDOERS_DIR"/*; do
            [[ -r "$f" ]] || continue
            while IFS= read -r line || [[ -n "$line" ]]; do
                if [[ "$line" =~ ^([^#][^[:space:]]+)[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:[[:space:]]+ALL$ ]]; then
                    PWLESS_USERS+=("${BASH_REMATCH[1]} ($f)")
                fi
            done < <(grep -hE '^[^#][^[:space:]]+[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:[[:space:]]+ALL' "$f" 2>/dev/null || true)
        done
    fi

    if [[ ${#PWLESS_USERS[@]} -gt 0 ]]; then
        OK "Users with passwordless sudo (${#PWLESS_USERS[@]}):"
        printf '             %s\n' "${PWLESS_USERS[@]}"
    else
        FAIL "No passwordless sudo users found"
    fi
}

check_glance_mount() {
    local directory="$GLANCE_MOUNT_DIR"
    local normalized_directory fstab_mount owner group permissions permission_mode

    [[ "$directory" == /* ]] || directory="/$directory"
    normalized_directory="${directory%/}"
    [[ -n "$normalized_directory" ]] || normalized_directory="/"

    fstab_mount=$(awk -v mount_point="$normalized_directory" '
        /^[[:space:]]*#/ || NF < 2 { next }
        {
            configured_mount = $2
            sub(/\/$/, "", configured_mount)
            if (configured_mount == "") configured_mount = "/"
            if (configured_mount == mount_point ||
                (mount_point != "/" && index(configured_mount, mount_point "/") == 1)) {
                print configured_mount
                exit
            }
        }
    ' /etc/fstab)
    if [[ -z "$fstab_mount" ]]; then
        WARN "No /etc/fstab mapping found at or below $normalized_directory; skipping directory checks"
        return
    fi
    OK "/etc/fstab contains a mapping for $fstab_mount"

    if [[ ! -d "$normalized_directory" ]]; then
        WARN "Directory $normalized_directory is not present; skipping permission and ownership checks"
        return
    fi

    permissions=$(stat -c '%A (%a)' "$normalized_directory")
    permission_mode=$(stat -c '%a' "$normalized_directory")
    owner=$(stat -c '%U' "$normalized_directory")
    group=$(stat -c '%G' "$normalized_directory")
    INFO "$normalized_directory has permissions: $permissions with owner: $owner; group: $group"

    if [[ "$permission_mode" == "755" ]]; then
        OK "$normalized_directory permissions are consistent (755)"
    else
        FAIL "$normalized_directory permissions are inconsistent: $permission_mode (expected 755)"
        INFO "Correct with: chmod 755 -- '$normalized_directory'"
    fi

    if [[ "$owner" == "pf9" && "$group" == "pf9group" ]]; then
        OK "$normalized_directory ownership is consistent (pf9:pf9group)"
    else
        FAIL "$normalized_directory ownership is inconsistent: $owner:$group (expected pf9:pf9group)"
        INFO "Correct with: chown pf9:pf9group -- '$normalized_directory'"
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
        local sync_status
        sync_status=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || true)
        if [[ "$sync_status" == "yes" ]]; then
            OK "System clock is synchronized by an NTP service"
        else
            FAIL "System clock synchronized: ${sync_status:-unknown}"
        fi
    else
        FAIL "timedatectl not available"
    fi
}

check_packages() {
    case "$PACKAGE_FAMILY" in
        deb)
            check_package_alternatives "SCSI device listing" lsscsi
            check_package_alternatives "SCSI generic utilities" sg3-utils
            check_package_alternatives "Device mapper multipath" multipath-tools
            check_package_alternatives "SCSI tools" scsitools
            check_package_alternatives "iSCSI initiator" open-iscsi
            check_package_alternatives "NFS client" nfs-common
            ;;
        rpm)
            check_package_alternatives "SCSI device listing" lsscsi
            check_package_alternatives "SCSI generic utilities" sg3_utils
            check_package_alternatives "Device mapper multipath" device-mapper-multipath
            check_package_alternatives "iSCSI initiator" iscsi-initiator-utils
            check_package_alternatives "NFS client" nfs-utils
            # EL provides rescan-scsi-bus.sh from its SCSI utility packaging; verify
            # the installed capability and report its actual RPM owner.
            check_command_provider "SCSI bus rescan utility" rescan-scsi-bus.sh
            ;;
    esac
}

check_services() {
    if ! command -v systemctl >/dev/null 2>&1; then
        FAIL "systemctl is unavailable"
        return
    fi

    for svc in iscsid multipathd; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            OK "$svc is running"
        elif [[ "$(service_load_state "$svc")" == "loaded" ]]; then
            FAIL "$svc is installed but not running"
        else
            FAIL "$svc is not installed"
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
        if ! command -v iscsiadm >/dev/null 2>&1; then
            FAIL "iscsiadm command not available"
            return
        fi
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
        local scsi_id_path
        scsi_id_path=$(command -v scsi_id 2>/dev/null || true)
        if [[ -n "$scsi_id_path" ]]; then
            INFO "Run: $scsi_id_path -gud </dev/diskname>  to get WWID for local drives"
        else
            INFO "Install the distribution's udev package to obtain scsi_id for local-drive WWID lookup"
        fi
        return
    fi

    local conf=/etc/multipath.conf

    # ── defaults section ──────────────────────────────────────────────────────
    local defaults_block
    defaults_block=$(awk '/^[[:space:]]*defaults[[:space:]]*\{/{f=1;next} f&&/^[[:space:]]*\}/{f=0;next} f{print}' "$conf")

    if [[ -z "$defaults_block" ]]; then
        FAIL "defaults{} section missing"
    else
        local key="checker_timeout" want="15" got
        got=$(printf '%s\n' "$defaults_block" | awk -v k="$key" '$1==k{print $2; exit}')
        if   [[ "$got" == "$want" ]]; then OK   "defaults: $key = $got"
        elif [[ -n "$got" ]];         then WARN "defaults: $key = $got  (expected: $want)"
        else                               FAIL "defaults: $key missing  (expected: $want)"
        fi
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
    printf '  %b[ NOTE ]%b  Review and Ensure the required host record (like netapp SVM IP etc) mapping is set for the SVM FQDN to be resolvable\n' "$RED" "$NC"
    INFO ""
    while IFS= read -r line; do INFO "$line"; done < /etc/hosts
}

check_group_consistency() {
    if ! command -v grpck >/dev/null 2>&1; then
        FAIL "grpck command not available"
        return
    fi

    local grpck_output
    if grpck_output=$(grpck -r 2>&1); then
        OK "Group database consistency check passed"
    else
        FAIL "Group database consistency check failed"
        while IFS= read -r line; do
            INFO "$line"
        done <<< "$grpck_output"
    fi
}

check_rsyslog_pf9_rules() {
    local rsyslog_dir="/etc/rsyslog.d"
    local log_paths=(
        "/var/log/pf9/ostackhost.log"
        "/var/log/pf9/cindervolume-base.log"
        "/var/log/pf9/hostagent.log"
        "/var/log/pf9/glance-api.log"
        "/var/log/pf9/novncproxy.log"
        "/var/log/pf9/pf9-neutron-ovn-metadata-agent.log"
    )

    if [[ ! -d "$rsyslog_dir" ]]; then
        FAIL "$rsyslog_dir directory not found"
        return
    fi

    local log_path
    for log_path in "${log_paths[@]}"; do
        local matching_files=()
        mapfile -t matching_files < <(
            grep -rlF -- "$log_path" "$rsyslog_dir" 2>/dev/null || true
        )

        if [[ ${#matching_files[@]} -gt 0 ]]; then
            OK "$log_path found in:"
            local rule_file
            for rule_file in "${matching_files[@]}"; do
                INFO "$rule_file"
            done
        else
            FAIL "$log_path not found in any file under $rsyslog_dir"
        fi
    done
}

check_pf9_user_group() {
    local user_name="pf9"
    local group_name="pf9group"
    local passwd_entry group_entry

    passwd_entry=$(getent passwd "$user_name" 2>/dev/null || true)
    if [[ -n "$passwd_entry" ]]; then
        OK "$passwd_entry"
    else
        FAIL "User $user_name not found"
    fi

    group_entry=$(getent group "$group_name" 2>/dev/null || true)
    if [[ -n "$group_entry" ]]; then
        OK "$group_entry"
    else
        FAIL "Group $group_name not found"
    fi
}

check_pf9_packages() {
    local pf9_packages=(
        pf9-cindervolume-base
        pf9-cindervolume-config
        pf9-comms
        pf9-glance-role
        pf9-ha-slave
        pf9-hostagent
        pf9-ip-discovery
        pf9-neutron-base
        pf9-neutron-ovn-controller
        pf9-neutron-ovn-metadata-agent
        pf9-ostackhost
    )
    local package_name

    case "$PACKAGE_FAMILY" in
        deb)
            check_package_alternatives "Open vSwitch common files" openvswitch-common
            check_package_alternatives "Open vSwitch service" openvswitch-switch
            check_package_alternatives "OVN common files" ovn-common
            check_package_alternatives "OVN host" ovn-host
            check_package_alternatives "Python Open vSwitch bindings" python3-openvswitch
            ;;
        rpm)
            # Package names vary with the enabled EL/PF9 repository. Check the
            # required installed executables and report their actual RPM owners.
            check_command_provider "Open vSwitch" ovs-vsctl
            check_command_provider "OVN host controller" ovn-controller
            if python3 -c 'import ovs' >/dev/null 2>&1; then
                OK "Python Open vSwitch bindings  (module: ovs)"
            else
                FAIL "Python Open vSwitch bindings  (python3 module 'ovs' unavailable)"
            fi
            ;;
    esac

    for package_name in "${pf9_packages[@]}"; do
        if package_is_installed "$package_name"; then
            OK "PF9 package: $package_name"
        else
            FAIL "PF9 package: $package_name  (not installed)"
        fi
    done
}

check_environment() {
    OK "Operating system: $OS_PRETTY_NAME"
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
        elif [[ "$(service_load_state "$unit")" == "loaded" ]]; then
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
        elif [[ "$(service_load_state pf9-remote-write.service)" == "loaded" ]]; then
            FAIL "pf9-remote-write.service: not running / failed"
        else
            WARN "pf9-remote-write.service: not installed"
        fi
    fi

    if [[ "$ostackhost_running" == true ]]; then
        local nova_conf="/opt/pf9/etc/nova/conf.d/nova_override.conf"
        printf "\n  %b[ nova_override.conf ]%b\n" "$CYAN" "$NC"
        if [[ -r "$nova_conf" ]]; then
            local vol_mp
            vol_mp=$(grep -E '^\s*volume_use_multipath\s*=' "$nova_conf" 2>/dev/null || true)
            if [[ -n "$vol_mp" ]]; then
                OK "volume_use_multipath: $vol_mp"
            else
                WARN "volume_use_multipath not set in nova_override.conf"
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
        local cinder_override_conf="/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf"
        printf "\n  %b[ cinder_override.conf ]%b\n" "$CYAN" "$NC"
        if [[ -r "$cinder_override_conf" ]]; then
            OK "cinder_override.conf found and readable"
            INFO ""
            INFO "── $cinder_override_conf ──"
            while IFS= read -r line; do INFO "$line"; done < "$cinder_override_conf"
        else
            WARN "cinder_override.conf not found or not readable: $cinder_override_conf"
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

check_virsh_responsiveness() {
    if ! command -v virsh >/dev/null 2>&1; then
        FAIL "virsh not installed"
        return
    fi

    local exit_code=0
    timeout 10 virsh list --all >/dev/null 2>&1 || exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        OK "virsh is responsive"
        return
    fi
    [[ $exit_code -eq 124 ]] \
        && FAIL "virsh is non-responsive (timed out after 10s)" \
        || FAIL "virsh is non-responsive (exit code: $exit_code)"

    local qemu_dir="/etc/libvirt/qemu"

    INFO "Scanning for defunct/zombie qemu processes..."
    local -a zombie_pids=()
    while IFS= read -r psline; do
        local pid stat
        pid=$(awk '{print $2}' <<< "$psline")
        stat=$(awk '{print $8}' <<< "$psline")
        [[ "$stat" == Z* ]] || continue
        zombie_pids+=("$pid")
        WARN "Defunct/zombie qemu process: PID $pid"
    done < <(ps aux | grep -E '[q]emu' || true)

    if [[ ${#zombie_pids[@]} -eq 0 ]]; then
        INFO "No defunct/zombie qemu processes found"
        return
    fi

    # Build PID → UUID map from libvirt runtime PID files
    local -A pid_uuid_map=()
    if [[ -d /var/run/libvirt/qemu ]]; then
        for pid_file in /var/run/libvirt/qemu/*.pid; do
            [[ -r "$pid_file" ]] || continue
            local d_name d_pid d_uuid
            d_name=$(basename "$pid_file" .pid)
            d_pid=$(< "$pid_file")
            if [[ -n "$d_pid" && -r "$qemu_dir/$d_name.xml" ]]; then
                d_uuid=$(grep '<uuid>' "$qemu_dir/$d_name.xml" 2>/dev/null \
                    | sed 's|.*<uuid>\(.*\)</uuid>.*|\1|' || true)
                [[ -n "$d_uuid" ]] && pid_uuid_map["$d_pid"]="$d_uuid"
            fi
        done
    fi

    for pid in "${zombie_pids[@]}"; do
        local uuid=""

        # Attempt 1: parse cmdline (empty for true zombies, may work for hung procs)
        local cmdline
        cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
        if [[ -n "$cmdline" ]]; then
            uuid=$(sed -n 's/.*-uuid \([a-f0-9-]\{36\}\).*/\1/p' <<< "$cmdline" || true)
            if [[ -z "$uuid" ]]; then
                local d_name
                d_name=$(sed -n 's/.*-name guest=\([^, ]*\).*/\1/p' <<< "$cmdline" \
                    | head -1 || true)
                if [[ -n "$d_name" && -r "$qemu_dir/$d_name.xml" ]]; then
                    uuid=$(grep '<uuid>' "$qemu_dir/$d_name.xml" 2>/dev/null \
                        | sed 's|.*<uuid>\(.*\)</uuid>.*|\1|' || true)
                fi
            fi
        fi

        # Attempt 2: PID file lookup (reliable for zombies whose cmdline is empty)
        [[ -z "$uuid" ]] && uuid="${pid_uuid_map[$pid]:-}"

        if [[ -z "$uuid" ]]; then
            WARN "PID $pid [defunct] — UUID not determinable (cmdline empty, no PID file match)"
            continue
        fi

        INFO "PID $pid [defunct] → UUID: $uuid"

        # Locate XML by UUID
        local xml_file=""
        if [[ -d "$qemu_dir" ]]; then
            xml_file=$(grep -rl "<uuid>${uuid}</uuid>" "$qemu_dir"/*.xml 2>/dev/null \
                | head -1 || true)
        fi
        if [[ -z "$xml_file" ]]; then
            WARN "  No XML found for UUID $uuid in $qemu_dir"
            continue
        fi

        # Extract dm-* block devices from the domain XML
        local -a dm_devs=()
        while IFS= read -r dev_path; do
            [[ -z "$dev_path" ]] && continue
            if [[ "$dev_path" =~ /dev/(dm-[0-9]+)$ ]]; then
                dm_devs+=("${BASH_REMATCH[1]}")
            elif [[ "$dev_path" == /dev/mapper/* ]]; then
                local resolved
                resolved=$(readlink -f "$dev_path" 2>/dev/null || true)
                [[ "$resolved" =~ /(dm-[0-9]+)$ ]] && dm_devs+=("${BASH_REMATCH[1]}")
            fi
        done < <(grep -oE "source dev='[^']+'" "$xml_file" 2>/dev/null \
            | sed "s/source dev='//;s/'$//" || true)

        if [[ ${#dm_devs[@]} -eq 0 ]]; then
            WARN "  No dm-* block devices found in $xml_file"
            continue
        fi

        for dm in "${dm_devs[@]}"; do
            INFO "  Multipath state for $dm:"
            local mp_block
            mp_block=$(multipath -ll 2>/dev/null | awk -v dm="$dm" '
                /^$/  { if (found) { print buf; found=0; buf="" }; next }
                found { buf = (buf != "") ? buf "\n" $0 : $0; next }
                index($0, dm) { found=1; buf=$0 }
                END   { if (found && buf != "") print buf }
            ' || true)
            if [[ -n "$mp_block" ]]; then
                while IFS= read -r mp_line; do
                    [[ -n "$mp_line" ]] && INFO "    $mp_line"
                done <<< "$mp_block"
            else
                WARN "    $dm not found in multipath -ll output"
            fi
        done
    done
}

check_multipath_orphans() {
    if ! command -v multipath >/dev/null 2>&1; then
        WARN "multipath command not available"
        return
    fi

    local mp_out
    mp_out=$(multipath -ll 2>/dev/null || true)
    if [[ -z "$mp_out" ]]; then
        WARN "No multipath devices found"
        return
    fi

    # Collect dm-* devices referenced by any VM XML in libvirt
    local qemu_dir="/etc/libvirt/qemu"
    local -A vm_dm_map=()
    if [[ -d "$qemu_dir" ]]; then
        for xml_file in "$qemu_dir"/*.xml; do
            [[ -r "$xml_file" ]] || continue
            local domain
            domain=$(basename "$xml_file" .xml)
            while IFS= read -r dev_path; do
                [[ -z "$dev_path" ]] && continue
                local dm=""
                if [[ "$dev_path" =~ /dev/(dm-[0-9]+)$ ]]; then
                    dm="${BASH_REMATCH[1]}"
                elif [[ "$dev_path" == /dev/mapper/* ]]; then
                    local resolved
                    resolved=$(readlink -f "$dev_path" 2>/dev/null || true)
                    [[ "$resolved" =~ /(dm-[0-9]+)$ ]] && dm="${BASH_REMATCH[1]}"
                fi
                [[ -n "$dm" ]] && vm_dm_map["$dm"]="$domain"
            done < <(grep -oE "source dev='[^']+'" "$xml_file" 2>/dev/null \
                | sed "s/source dev='//;s/'$//" || true)
        done
    fi

    # Split multipath -ll output into per-device stanzas
    local -a s_maps=() s_dms=() s_blocks=()
    local cur_map="" cur_dm="" cur_block=""
    while IFS= read -r line; do
        if [[ -z "$line" ]]; then
            if [[ -n "$cur_map" ]]; then
                s_maps+=("$cur_map"); s_dms+=("$cur_dm"); s_blocks+=("$cur_block")
                cur_map=""; cur_dm=""; cur_block=""
            fi
            continue
        fi
        # Device header: non-indented line containing dm-X
        if [[ "$line" =~ ^[^[:space:]] ]] && [[ "$line" =~ (dm-[0-9]+) ]]; then
            if [[ -n "$cur_map" ]]; then
                s_maps+=("$cur_map"); s_dms+=("$cur_dm"); s_blocks+=("$cur_block")
            fi
            cur_map=$(awk '{print $1}' <<< "$line")
            cur_dm="${BASH_REMATCH[1]}"
            cur_block="$line"
        else
            cur_block="${cur_block:+$cur_block$'\n'}$line"
        fi
    done <<< "$mp_out"
    if [[ -n "$cur_map" ]]; then
        s_maps+=("$cur_map"); s_dms+=("$cur_dm"); s_blocks+=("$cur_block")
    fi

    local found_issues=false
    for ((i = 0; i < ${#s_maps[@]}; i++)); do
        local map="${s_maps[$i]}" dm="${s_dms[$i]}" block="${s_blocks[$i]}"
        local used_by="${vm_dm_map[$dm]:-}"

        if [[ -z "$used_by" ]]; then
            found_issues=true
            WARN "Orphan: $map ($dm) — not referenced by any VM XML"
            while IFS= read -r l; do [[ -n "$l" ]] && INFO "  $l"; done <<< "$block"
        fi

        local faulty
        faulty=$(grep -E '\b(failed|faulty)\b' <<< "$block" || true)
        if [[ -n "$faulty" ]]; then
            found_issues=true
            FAIL "Failed/faulty paths on $map ($dm)${used_by:+  [VM: $used_by]}:"
            echo "--------------------------------------------------------------"
            echo " "
            # Skip re-printing path lines for orphans — already shown in the stanza dump above
            if [[ -n "$used_by" ]]; then
                while IFS= read -r l; do [[ -n "$l" ]] && INFO "  $l"; done <<< "$faulty"
            fi
        fi
    done

    [[ "$found_issues" == false ]] && OK "All multipath devices are VM-referenced with healthy paths"
}

check_vm_disk_multipath() {
    if ! command -v virsh >/dev/null 2>&1; then
        FAIL "virsh not installed"
        return
    fi

    local running_vms exit_code=0
    running_vms=$(timeout 10 virsh list --name 2>/dev/null) || exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        WARN "virsh unresponsive — skipping VM disk multipath check"
        return
    fi
    running_vms=$(grep -v '^$' <<< "$running_vms" || true)
    if [[ -z "$running_vms" ]]; then
        INFO "No running VMs"
        return
    fi

    # Pre-parse multipath -ll once into dm-X keyed maps
    local -A mp_map_name=() mp_stanza=()
    local mp_out
    mp_out=$(multipath -ll 2>/dev/null || true)
    if [[ -n "$mp_out" ]]; then
        local cur_map="" cur_dm="" cur_block=""
        while IFS= read -r line; do
            if [[ -z "$line" ]]; then
                if [[ -n "$cur_dm" ]]; then
                    mp_map_name["$cur_dm"]="$cur_map"
                    mp_stanza["$cur_dm"]="$cur_block"
                    cur_map=""; cur_dm=""; cur_block=""
                fi
                continue
            fi
            if [[ "$line" =~ ^[^[:space:]] ]] && [[ "$line" =~ (dm-[0-9]+) ]]; then
                if [[ -n "$cur_dm" ]]; then
                    mp_map_name["$cur_dm"]="$cur_map"
                    mp_stanza["$cur_dm"]="$cur_block"
                fi
                cur_map=$(awk '{print $1}' <<< "$line")
                cur_dm="${BASH_REMATCH[1]}"
                cur_block="$line"
            else
                cur_block="${cur_block:+$cur_block$'\n'}$line"
            fi
        done <<< "$mp_out"
        if [[ -n "$cur_dm" ]]; then
            mp_map_name["$cur_dm"]="$cur_map"
            mp_stanza["$cur_dm"]="$cur_block"
        fi
    fi

    local qemu_dir="/etc/libvirt/qemu"

    while IFS= read -r vm; do
        [[ -z "$vm" ]] && continue

        local uuid
        uuid=$(virsh dominfo "$vm" 2>/dev/null | awk '/^UUID:/{print $2}' || true)
        printf "\n  ${CYAN}VM: %-48s${NC} UUID: %s\n" "$vm" "${uuid:-unknown}"

        # Get DM devices: virsh domblklist preferred, XML fallback
        local -a dm_devs=()
        local domblk
        domblk=$(virsh domblklist --details "$vm" 2>/dev/null || true)
        if [[ -n "$domblk" ]]; then
            mapfile -t dm_devs < <(awk '{print $4}' <<< "$domblk" \
                | grep -oE 'dm-[0-9]+' | sort -u)
        fi
        if [[ ${#dm_devs[@]} -eq 0 && -r "$qemu_dir/$vm.xml" ]]; then
            while IFS= read -r dev_path; do
                [[ -z "$dev_path" ]] && continue
                if [[ "$dev_path" =~ /dev/(dm-[0-9]+)$ ]]; then
                    dm_devs+=("${BASH_REMATCH[1]}")
                elif [[ "$dev_path" == /dev/mapper/* ]]; then
                    local resolved
                    resolved=$(readlink -f "$dev_path" 2>/dev/null || true)
                    [[ "$resolved" =~ /(dm-[0-9]+)$ ]] && dm_devs+=("${BASH_REMATCH[1]}")
                fi
            done < <(grep -oE "source dev='[^']+'" "$qemu_dir/$vm.xml" 2>/dev/null \
                | sed "s/source dev='//;s/'$//" || true)
        fi

        if [[ ${#dm_devs[@]} -eq 0 ]]; then
            WARN "No DM-* block devices found for $vm"
            continue
        fi

        for dm in "${dm_devs[@]}"; do
            local map="${mp_map_name[$dm]:-}"
            local stanza="${mp_stanza[$dm]:-}"

            if [[ -z "$map" ]]; then
                FAIL "$dm  →  not found in multipath"
                continue
            fi

            # Count total paths (lines with H:B:T:L) and active+ready ones
            local total active
            total=$(grep -cE '[0-9]+:[0-9]+:[0-9]+:[0-9]+' <<< "$stanza" || true)
            active=$(grep -E '[0-9]+:[0-9]+:[0-9]+:[0-9]+' <<< "$stanza" \
                | grep -cE '\bactive\b.*\bready\b' || true)

            if   [[ "$total" -gt 0 && "$active" -eq "$total" ]]; then
                OK   "$dm  →  $map  active ($active/$total paths up)"
            elif [[ "$active" -gt 0 ]]; then
                WARN "$dm  →  $map  degraded ($active/$total paths up)"
            else
                FAIL "$dm  →  $map  dead (0/${total:-?} paths active)"
            fi
        done
    done <<< "$running_vms"
}


# check-mpath-orphan / list-vm-mpath / check-glance-mount are standalone checks: when any is requested,
# run only the requested check(s) and skip the full default suite below.
health_check "ENVIRONMENT" check_environment

if [[ "$CHECK_MPATH_ORPHAN" == true || "$LIST_VM_MPATH" == true || "$CHECK_GLANCE_MOUNT" == true ]]; then
    [[ "$CHECK_MPATH_ORPHAN" == true ]] && health_check "MULTIPATH ORPHANS"  check_multipath_orphans
    [[ "$LIST_VM_MPATH"      == true ]] && health_check "VM DISK MULTIPATH"   check_vm_disk_multipath
    [[ "$CHECK_GLANCE_MOUNT" == true ]] && health_check "GLANCE IMAGE MOUNT" check_glance_mount
else
    [[ "$CHECK_SUDOERS" == true ]] && health_check "1.  PASSWORDLESS SUDO"   check_sudoers

    health_check "CHECK BOND MODE"     check_bond
    health_check "NTP (Mandatory check to pass)"                 check_ntp
    health_check "PACKAGES"            check_packages
    health_check "SERVICES"            check_services
    health_check "ISCSI INITIATOR (to be referred for iSCSI backend)"     check_iscsi_initiator
    health_check "ISCSID CONF"         check_iscsid_conf
    health_check "MULTIPATH BLACKLIST"  check_multipath_blacklist
    health_check "LVM FILTERS"         check_lvm_filters
    health_check "PF9 PACKAGES"        check_pf9_packages
    health_check "PF9 SERVICES"        check_pf9_services
    health_check "OVS BRIDGES"         check_ovs_bridges

    health_check "/ETC/HOSTS entries"              check_hosts
    health_check "VIRSH LIVENESS"          check_virsh_responsiveness
    health_check "GROUP CONSISTENCY (local /etc/group consistency check)"       check_group_consistency
    health_check "RSYSLOG PF9 RULES"        check_rsyslog_pf9_rules
    health_check "PF9 USER AND GROUP (requires to be consistent across all hosts)"       check_pf9_user_group

    if [[ -n "$VIRSH_UUID" ]]; then
        health_check "16. VIRSH VMS"           check_virsh_vms "$VIRSH_UUID"
    fi
fi
