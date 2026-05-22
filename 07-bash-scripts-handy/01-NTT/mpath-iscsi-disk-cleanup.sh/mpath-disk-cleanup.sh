#!/usr/bin/env bash
# Inspect orphaned or VM-attached multipath devices and emit flat lists of
# mpath IDs and their underlying sd* paths for use in cleanup workflows.

set -euo pipefail

# ── Arg parsing ───────────────────────────────────────────────────────────────
SHOW_ORPHANS=false
SHOW_VM_MPATH=false
SHOW_CLEANUP=false
DRY_RUN=true
OUTPUT_DIR="."
LOG_FILE=""

usage() {
    cat <<EOF
Usage: $0 <command> [command ...] [--output-dir <dir>] [--execute]

Commands (at least one required):
  orphans     Report multipath devices not referenced by any VM XML
  vm-mpath    Report per-VM DM disk multipath state
  cleanup     Remove orphaned mpath maps and their underlying SCSI paths
              (requires orphans; dry-run by default — add --execute to apply)

Options:
  --output-dir <dir>   Write output files to <dir> (default: current directory)
  --execute            Arm live removal for the cleanup command (default: dry-run)
  -h | --help          Show this help

Output files written to OUTPUT_DIR:
  mpath-ids-<host>-<timestamp>.txt      One mpath alias/WWID per line
  mpath-sd-devices-<host>-<timestamp>.txt   One sd* device per line
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        orphans)       SHOW_ORPHANS=true ;;
        vm-mpath)      SHOW_VM_MPATH=true ;;
        cleanup)       SHOW_CLEANUP=true ;;
        --output-dir)  shift; OUTPUT_DIR="$1" ;;
        --execute)     DRY_RUN=false ;;
        -h|--help)     usage ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            ;;
    esac
    shift
done

if [[ "$SHOW_ORPHANS" == false && "$SHOW_VM_MPATH" == false && "$SHOW_CLEANUP" == false ]]; then
    echo "ERROR: specify at least one command (orphans | vm-mpath | cleanup)" >&2
    usage
fi

if [[ "$SHOW_CLEANUP" == true && "$SHOW_ORPHANS" == false ]]; then
    echo "ERROR: cleanup requires orphans to be specified (e.g. $0 orphans cleanup)" >&2
    usage
fi

# ── Color helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

OK()   { printf "  ${GREEN}[ OK ]${NC}  %s\n" "$*";    log_to_file "[ OK ]   $*"; }
FAIL() { printf "  ${RED}[ FAIL ]${NC}  %s\n" "$*";  log_to_file "[ FAIL ] $*"; }
WARN() { printf "  ${YELLOW}[ WARN ]${NC}  %s\n" "$*"; log_to_file "[ WARN ] $*"; }
INFO() { printf "  ${DIM}         ${NC}  %s\n" "$*"; log_to_file "         $*"; }

section() { printf "\n${CYAN}${BOLD}━━━  %-30s━━━${NC}\n" "$1 "; log_to_file "━━━  $1 ━━━"; }

# ── Logger ────────────────────────────────────────────────────────────────────
# Appends a timestamped plain-text line to LOG_FILE. No-op when LOG_FILE is unset.
log_to_file() {
    [[ -z "$LOG_FILE" ]] && return 0
    printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

# ── Global mpath tables (populated by parse_multipath_ll) ─────────────────────
declare -A mp_map_name=()   # dm-X  → alias/WWID
declare -A mp_stanza=()     # dm-X  → full stanza text

parse_multipath_ll() {
    if ! command -v multipath >/dev/null 2>&1; then
        echo "ERROR: multipath command not found" >&2
        exit 1
    fi

    local mp_out
    mp_out=$(multipath -ll 2>/dev/null || true)
    if [[ -z "$mp_out" ]]; then
        WARN "multipath -ll returned no output"
        return
    fi

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
    [[ -n "$cur_dm" ]] && { mp_map_name["$cur_dm"]="$cur_map"; mp_stanza["$cur_dm"]="$cur_block"; }
}

# ── VM → dm-X map (populated by collect_vm_dm_map) ────────────────────────────
declare -A vm_dm_map=()   # dm-X → domain name

collect_vm_dm_map() {
    local qemu_dir="/etc/libvirt/qemu"
    [[ -d "$qemu_dir" ]] || return
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
}

# Collected dm devices for output files (appended to by each check function)
declare -a collected_dms=()

# ── check_dm_host_usage ───────────────────────────────────────────────────────
# Silent predicate: returns 0 if dm is NOT consumed anywhere on this host,
# 1 if any consumer is found (mount, sysfs holder, LVM PV, MD RAID, open fd).
check_dm_host_usage() {
    local dm="$1"    # e.g. dm-3
    local map="$2"   # mpath alias or WWID

    # Mounted filesystem
    awk -v dm="/dev/${dm}" -v mp="/dev/mapper/${map}" \
        '$1==dm||$1==mp{found=1}END{exit !found}' /proc/mounts 2>/dev/null \
        && return 1

    # Sysfs holders (LVM LVs, MD arrays stacked on top)
    local holders_dir="/sys/block/${dm}/holders"
    if [[ -d "$holders_dir" ]]; then
        local -a holders=()
        mapfile -t holders < <(ls "$holders_dir" 2>/dev/null || true)
        [[ ${#holders[@]} -gt 0 ]] && return 1
    fi

    # LVM physical volume
    if command -v pvs >/dev/null 2>&1; then
        pvs "/dev/${dm}" >/dev/null 2>&1 && return 1
    fi

    # MD RAID member
    grep -qsE "\b${dm}\b" /proc/mdstat 2>/dev/null && return 1

    # Open file descriptors
    if command -v lsof >/dev/null 2>&1; then
        lsof "/dev/${dm}" 2>/dev/null | grep -q . && return 1
    fi

    return 0
}

# ── report_dm_host_usage ─────────────────────────────────────────────────────
# Prints one INFO line per consumer found on this host.
# Returns 0 if no consumers exist (safe to queue for cleanup),
# 1 if any consumer was found (device is actively used).
report_dm_host_usage() {
    local dm="$1"   # e.g. dm-3
    local map="$2"  # mpath alias or WWID
    local consumed=0

    # Mounted filesystem
    local mnt
    mnt=$(awk -v dm="/dev/${dm}" -v mp="/dev/mapper/${map}" \
        '$1==dm||$1==mp{print $2}' /proc/mounts 2>/dev/null | head -1 || true)
    if [[ -n "$mnt" ]]; then
        INFO "  [HOST] mounted at: $mnt"
        consumed=1
    fi

    # Sysfs holders (LVM LVs, MD arrays stacked on top).
    # Verify each holder is live in /dev — sysfs entries can persist as stale
    # after a device is torn down without a clean holder release.
    local holders_dir="/sys/block/${dm}/holders"
    if [[ -d "$holders_dir" ]]; then
        local holder
        while IFS= read -r holder; do
            [[ -z "$holder" ]] && continue
            if dmsetup info "$holder" >/dev/null 2>&1; then
                INFO "  [HOST] sysfs holder: $holder"
                consumed=1
            else
                INFO "  [HOST] stale sysfs holder (device gone): $holder — ignored"
            fi
        done < <(ls "$holders_dir" 2>/dev/null || true)
    fi

    # LVM physical volume
    if command -v pvs >/dev/null 2>&1; then
        if pvs "/dev/${dm}" >/dev/null 2>&1; then
            local vg
            vg=$(pvs --noheadings -o vg_name "/dev/${dm}" 2>/dev/null \
                | awk '{$1=$1; print}' | head -1 || true)
            if [[ -n "$vg" ]]; then
                INFO "  [HOST] LVM PV — VG: $vg"
            else
                INFO "  [HOST] LVM PV — orphan PV (no VG assigned)"
            fi
            consumed=1
        fi
    fi

    # MD RAID member
    if grep -qsE "\b${dm}\b" /proc/mdstat 2>/dev/null; then
        local md_arr
        md_arr=$(grep -E "\b${dm}\b" /proc/mdstat | awk '{print $1}' | head -1 || true)
        INFO "  [HOST] MD RAID member: ${md_arr:-unknown array}"
        consumed=1
    fi

    # Open file descriptors — lsof preferred, fuser as fallback
    if command -v lsof >/dev/null 2>&1; then
        local procs
        procs=$(lsof "/dev/${dm}" 2>/dev/null \
            | awk 'NR>1{print $1"(PID:"$2")"}' | sort -u | head -5 || true)
        if [[ -n "$procs" ]]; then
            INFO "  [HOST] open by: $(tr '\n' ' ' <<< "$procs")"
            consumed=1
        fi
    elif command -v fuser >/dev/null 2>&1; then
        local fuser_out
        fuser_out=$(fuser "/dev/${dm}" 2>/dev/null || true)
        if [[ -n "$fuser_out" ]]; then
            INFO "  [HOST] fuser PIDs: $fuser_out"
            consumed=1
        fi
    fi

    return $consumed   # 0 = no consumers (safe), 1 = consumed (skip)
}

# ── check_multipath_orphans ───────────────────────────────────────────────────
check_multipath_orphans() {
    section "MULTIPATH ORPHANS"

    if [[ ${#mp_map_name[@]} -eq 0 ]]; then
        WARN "No multipath devices found"
        return
    fi

    local found_issues=false
    for dm in "${!mp_map_name[@]}"; do
        local map="${mp_map_name[$dm]}"
        local block="${mp_stanza[$dm]}"
        local used_by="${vm_dm_map[$dm]:-}"

        if [[ -z "$used_by" ]]; then
            found_issues=true
            WARN "Orphan: $map ($dm) — not referenced by any VM XML"
            while IFS= read -r l; do [[ -n "$l" ]] && INFO "  $l"; done <<< "$block"
            # Report and gate: only queue if nothing on this host is consuming the device
            if report_dm_host_usage "$dm" "$map"; then
                INFO "  no host consumers — queued for cleanup"
                collected_dms+=("$dm")
            else
                INFO "  skipped: device has active host consumers (see above)"
            fi
        fi

        local faulty
        faulty=$(grep -E '\b(failed|faulty)\b' <<< "$block" || true)
        if [[ -n "$faulty" ]]; then
            found_issues=true
            FAIL "Failed/faulty paths on $map ($dm)${used_by:+  [VM: $used_by]}:"
            if [[ -n "$used_by" ]]; then
                while IFS= read -r l; do [[ -n "$l" ]] && INFO "  $l"; done <<< "$faulty"
            fi
        fi
    done

    if [[ "$found_issues" == false ]]; then
        OK "All multipath devices are VM-referenced with healthy paths"
    fi
}

# ── check_vm_disk_multipath ───────────────────────────────────────────────────
check_vm_disk_multipath() {
    section "VM DISK MULTIPATH"

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

    local qemu_dir="/etc/libvirt/qemu"

    while IFS= read -r vm; do
        [[ -z "$vm" ]] && continue

        local uuid
        uuid=$(virsh dominfo "$vm" 2>/dev/null | awk '/^UUID:/{print $2}' || true)
        printf "\n  ${CYAN}VM: %-48s${NC} UUID: %s\n" "$vm" "${uuid:-unknown}"

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

# ── Write output files ────────────────────────────────────────────────────────
write_output_files() {
    section "OUTPUT FILES"

    if [[ ${#collected_dms[@]} -eq 0 ]]; then
        WARN "No mpath devices collected — output files not written"
        return
    fi

    mkdir -p "$OUTPUT_DIR" || { FAIL "Cannot create output directory: $OUTPUT_DIR"; return 1; }
    [[ -w "$OUTPUT_DIR" ]] || { FAIL "Output directory not writable: $OUTPUT_DIR"; return 1; }

    local ts host
    ts=$(date '+%Y%m%d_%H%M%S')
    host=$(hostname -s)
    local ids_file="${OUTPUT_DIR}/mpath-ids-orphans-${host}-${ts}.txt"
    local sd_file="${OUTPUT_DIR}/mpath-sd-devices-orphans-${host}-${ts}.txt"
    local assoc_file="${OUTPUT_DIR}/mpath-assoc-orphans-${host}-${ts}.txt"

    # Deduplicate preserving insertion order
    local -A seen=()
    local -a unique_dms=()
    for dm in "${collected_dms[@]}"; do
        [[ -n "${seen[$dm]:-}" ]] && continue
        seen[$dm]=1
        unique_dms+=("$dm")
    done

    : > "$ids_file"   || { FAIL "Cannot create: $ids_file";   return 1; }
    : > "$sd_file"    || { FAIL "Cannot create: $sd_file";    return 1; }
    : > "$assoc_file" || { FAIL "Cannot create: $assoc_file"; return 1; }

    for dm in "${unique_dms[@]}"; do
        local stanza="${mp_stanza[$dm]}"

        # WWID: header line whose first field is a 32-char lowercase hex string.
        # Falls back to the alias/WWID stored during parse if the pattern yields nothing
        # (e.g. aliased maps where the WWID sits inside parentheses on the header line).
        local wwid
        wwid=$(awk '/^[0-9a-f]{32}/ { print $1; exit }' <<< "$stanza" || true)
        if [[ -z "$wwid" ]]; then
            wwid=$(grep -oE '\([0-9a-f]{32}\)' <<< "${stanza%%$'\n'*}" \
                | tr -d '()' | head -1 || true)
        fi
        [[ -z "$wwid" ]] && wwid="${mp_map_name[$dm]}"

        # sd* devices: extracted from H:B:T:L path lines only
        local sd_devs
        sd_devs=$(awk '/[0-9]+:[0-9]+:[0-9]+:[0-9]+/ {
            for (i=1; i<=NF; i++) if ($i ~ /^sd[a-z]+$/) print $i
        }' <<< "$stanza" || true)

        echo "$wwid" >> "$ids_file"
        [[ -n "$sd_devs" ]] && echo "$sd_devs" >> "$sd_file"
        printf "%s  %s\n" "$wwid" "$(tr '\n' ' ' <<< "$sd_devs" | sed 's/ $//')" >> "$assoc_file"
    done

    printf "  %-60s  (%d entries)\n" "$ids_file"   "$(wc -l < "$ids_file"   | tr -d ' ')"
    printf "  %-60s  (%d entries)\n" "$sd_file"    "$(wc -l < "$sd_file"    | tr -d ' ')"
    printf "  %-60s  (%d entries)\n" "$assoc_file" "$(wc -l < "$assoc_file" | tr -d ' ')"
}

# ── perform_cleanup ───────────────────────────────────────────────────────────
# Flushes each orphaned mpath map then removes its underlying SCSI path devices.
# Operates only on collected_dms — devices already verified as orphans with no
# active host consumers. Dry-run by default; pass --execute to arm live removal.
perform_cleanup() {
    local ts host mode_tag
    ts=$(date '+%Y%m%d_%H%M%S')
    host=$(hostname -s)
    if [[ "$DRY_RUN" == true ]]; then mode_tag="dryrun"; else mode_tag="execute"; fi
    mkdir -p "$OUTPUT_DIR" 2>/dev/null || true
    LOG_FILE="${OUTPUT_DIR}/mpath-cleanup-${mode_tag}-${host}-${ts}.log"
    : > "$LOG_FILE" 2>/dev/null || { printf "WARN: cannot create log file: %s\n" "$LOG_FILE" >&2; LOG_FILE=""; }

    section "MULTIPATH CLEANUP"

    if [[ ${#collected_dms[@]} -eq 0 ]]; then
        INFO "No orphaned devices queued — nothing to clean up"
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        WARN "Dry run — pass --execute to perform actual removal"
    fi

    # Deduplicate preserving insertion order (mirrors write_output_files)
    local -A seen=()
    local -a unique_dms=()
    for dm in "${collected_dms[@]}"; do
        [[ -n "${seen[$dm]:-}" ]] && continue
        seen[$dm]=1
        unique_dms+=("$dm")
    done

    local cleaned=0 failed=0

    for dm in "${unique_dms[@]}"; do
        local map="${mp_map_name[$dm]}"
        local stanza="${mp_stanza[$dm]}"

        local -a sd_devs=()
        mapfile -t sd_devs < <(awk '/[0-9]+:[0-9]+:[0-9]+:[0-9]+/{
            for (i=1;i<=NF;i++) if ($i~/^sd[a-z]+$/) print $i
        }' <<< "$stanza" 2>/dev/null || true)

        printf "\n"
        INFO "Target: $map ($dm) — paths: ${sd_devs[*]:-none}"

        # ── Step 1: flush multipath map ──────────────────────────────────────
        if [[ "$DRY_RUN" == true ]]; then
            INFO "  [DRY RUN] multipath -f $map"
        else
            if multipath -f "$map" >/dev/null 2>&1; then
                OK "  Flushed multipath map: $map"
            else
                FAIL "  multipath -f $map failed — skipping SCSI path removal"
                failed=$(( failed + 1 ))
                continue
            fi
        fi

        # ── Step 2: remove each underlying SCSI path device ─────────────────
        for sd in "${sd_devs[@]}"; do
            local delete_path="/sys/block/${sd}/device/delete"
            if [[ "$DRY_RUN" == true ]]; then
                INFO "  [DRY RUN] echo 1 > $delete_path"
            else
                if [[ -w "$delete_path" ]]; then
                    if echo 1 > "$delete_path" 2>/dev/null; then
                        OK "  Removed SCSI path: $sd"
                    else
                        FAIL "  Failed to remove SCSI path: $sd"
                        failed=$(( failed + 1 ))
                    fi
                else
                    WARN "  $sd: sysfs delete path not found — already removed?"
                fi
            fi
        done

        cleaned=$(( cleaned + 1 ))
    done

    printf "\n"
    if [[ "$DRY_RUN" == false ]]; then
        if [[ $cleaned -gt 0 ]]; then OK "Cleanup complete: $cleaned device(s) processed"; fi
        if [[ $failed  -gt 0 ]]; then FAIL "$failed device(s) had errors — review output above"; fi
    else
        INFO "Dry run: ${#unique_dms[@]} device(s) would be processed — rerun with --execute to apply"
    fi
    if [[ -n "$LOG_FILE" ]]; then INFO "Log: $LOG_FILE"; fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
parse_multipath_ll
collect_vm_dm_map

[[ "$SHOW_ORPHANS"  == true ]] && check_multipath_orphans
[[ "$SHOW_VM_MPATH" == true ]] && check_vm_disk_multipath

[[ "$SHOW_ORPHANS"  == true ]] && write_output_files
[[ "$SHOW_CLEANUP"  == true ]] && perform_cleanup
