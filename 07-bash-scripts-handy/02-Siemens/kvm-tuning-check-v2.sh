#!/usr/bin/env bash
# =============================================================================
# kvm_quick_check.sh
# Checks current state of tunings A-I for Ubuntu 22.04 5.15-generic KVM host
# Usage: sudo bash kvm_quick_check.sh
# =============================================================================

set -uo pipefail

# ── colour ────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  R='\033[0;31m' Y='\033[0;33m' G='\033[0;32m'
  C='\033[0;36m' B='\033[1m'   X='\033[0m'
else
  R='' Y='' G='' C='' B='' X=''
fi

PASS=0; WARN=0; FAIL=0

_hdr() { echo -e "\n${B}── $* ──${X}"; }
ok()   { echo -e "  ${G}[OK]  ${X} $1"; echo -e "         value : ${C}$2${X}"; ((++PASS)); }
warn() { echo -e "  ${Y}[WARN]${X} $1"; echo -e "         value : ${C}$2${X}  want: ${B}$3${X}"; ((++WARN)); }
fail() { echo -e "  ${R}[FAIL]${X} $1"; echo -e "         value : ${C}$2${X}  want: ${B}$3${X}"; ((++FAIL)); }
inf()  { echo -e "         ${C}$1${X}"; }

sysctl_val() { sysctl -n "$1" 2>/dev/null || echo "UNSET"; }
file_val()   { [[ -r "$1" ]] && cat "$1" 2>/dev/null || echo "UNREAD"; }
has_param()  { grep -q "$1" /proc/cmdline 2>/dev/null && echo "yes" || echo ""; }
get_param()  { grep -oP "${1}=\S+" /proc/cmdline 2>/dev/null | head -1 || echo ""; }

echo -e "\n${B}KVM Tuning Quick Check — $(uname -r) — $(date '+%Y-%m-%d %H:%M')${X}"
[[ $EUID -ne 0 ]] && echo -e "  ${Y}[!] Not root — some reads may fail${X}"

# =============================================================================
_hdr "A. GRUB CMDLINE"
# =============================================================================

CMDLINE=$(cat /proc/cmdline)
inf "cmdline: $CMDLINE"

check_param() {
  local label="$1" pattern="$2" want="$3"
  local found; found=$(get_param "$pattern")
  [[ -z "$found" ]] && [[ -n "$(has_param "$pattern")" ]] && found="$pattern"
  if [[ -n "$found" ]]; then ok  "$label" "$found"
  else                        fail "$label" "not set" "$want"; fi
}

check_param "preempt=full"             "preempt"               "preempt=full"
check_param "processor.max_cstate=1"  "processor.max_cstate"  "processor.max_cstate=1"
check_param "amd_pstate"              "amd_pstate"            "amd_pstate=passive"
check_param "transparent_hugepage"    "transparent_hugepage"  "transparent_hugepage=madvise"
check_param "isolcpus"                "isolcpus"              "isolcpus=nohz,domain,N-M"
check_param "nohz_full"               "nohz_full"             "nohz_full=N-M"
check_param "rcu_nocbs"               "rcu_nocbs"             "rcu_nocbs=N-M"
check_param "skew_tick=1"             "skew_tick"             "skew_tick=1"
check_param "tsc=reliable"            "tsc"                   "tsc=reliable"
check_param "nosoftlockup"            "nosoftlockup"          "nosoftlockup"

# =============================================================================
_hdr "B. CPU GOVERNOR"
# =============================================================================

GOV=$(file_val /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
DRV=$(file_val /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver)
inf "driver: $DRV"

[[ "$GOV" == "performance" ]] \
  && ok   "scaling_governor" "$GOV" \
  || fail "scaling_governor" "$GOV" "performance"

BAD=0
for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [[ -r "$f" ]] && g=$(cat "$f") && [[ "$g" != "performance" ]] && ((BAD++))
done
[[ $BAD -eq 0 ]] \
  && ok   "all cores on performance" "0 mismatched" \
  || fail "cores not on performance" "$BAD core(s)" "0"

if [[ -r /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference ]]; then
  EPP=$(file_val /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference)
  [[ "$EPP" == "performance" ]] \
    && ok   "energy_performance_preference" "$EPP" \
    || warn "energy_performance_preference" "$EPP" "performance"
else
  inf "EPP not available for driver $DRV"
fi

for svc in thermald power-profiles-daemon; do
  S=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
  [[ "$S" == "inactive" || "$S" == "not-found" ]] \
    && ok   "$svc" "inactive" \
    || fail "$svc" "$S (active — overrides governor)" "inactive"
done

SVC=$(systemctl is-active cpupower-performance.service 2>/dev/null || echo "not-found")
[[ "$SVC" == "active" ]] \
  && ok   "cpupower-performance.service" "active" \
  || warn "cpupower-performance.service" "$SVC" "active (governor may not persist across reboots)"

# =============================================================================
_hdr "C. SYSCTL"
# =============================================================================

check_sc() {
  local key="$1" want="$2" op="${3:-eq}"
  local cur; cur=$(sysctl_val "$key")
  case "$op" in
    eq)  if [[ "$cur" == "$want" ]];                             then ok "$key" "$cur"; else fail "$key" "$cur" "$want";     fi ;;
    le)  if [[ "$cur" != "UNSET" ]] && (( cur <= want ));        then ok "$key" "$cur"; else fail "$key" "$cur" "<= $want"; fi ;;
    ge)  if [[ "$cur" != "UNSET" ]] && (( cur >= want ));        then ok "$key" "$cur"; else fail "$key" "$cur" ">= $want"; fi ;;
  esac
}

check_sc "vm.overcommit_memory"           "1"
check_sc "vm.swappiness"                  "10"  le
check_sc "vm.vfs_cache_pressure"          "50"  le
check_sc "vm.compaction_proactiveness"    "0"
check_sc "vm.dirty_ratio"                 "15"  le
check_sc "vm.dirty_background_ratio"      "5"   le
check_sc "vm.dirty_expire_centisecs"      "500" le
check_sc "vm.dirty_writeback_centisecs"   "100" le
check_sc "kernel.numa_balancing"          "0"
check_sc "kernel.sched_min_granularity_ns"    "4000000" le
check_sc "kernel.sched_wakeup_granularity_ns" "2000000" le
check_sc "kernel.sched_migration_cost_ns"     "3000000" ge
check_sc "kernel.sched_latency_ns"            "12000000" le
check_sc "kernel.watchdog"                "0"
check_sc "kernel.nmi_watchdog"            "0"
check_sc "net.core.rmem_max"              "134217728" ge
check_sc "net.core.wmem_max"              "134217728" ge
check_sc "net.core.netdev_max_backlog"    "5000"      ge
check_sc "net.core.somaxconn"             "4096"      ge
check_sc "net.ipv4.tcp_congestion_control" "bbr"
check_sc "net.core.default_qdisc"         "fq"
check_sc "fs.aio_max_nr"                  "1048576" ge

# =============================================================================
_hdr "D. I/O SCHEDULER"
# =============================================================================

DEVS=$(lsblk -d -n -o NAME,TYPE 2>/dev/null | awk '$2=="disk"{print $1}')
if [[ -z "$DEVS" ]]; then
  warn "block devices" "none found" "at least one disk"
else
  for dev in $DEVS; do
    SCHED=$(file_val /sys/block/${dev}/queue/scheduler)
    ROT=$(file_val   /sys/block/${dev}/queue/rotational)
    NR=$(file_val    /sys/block/${dev}/queue/nr_requests)
    RA=$(file_val    /sys/block/${dev}/queue/read_ahead_kb)
    inf "${dev}: rotational=${ROT}  nr_requests=${NR}  read_ahead_kb=${RA}"
    if   [[ "$dev" == nvme* ]]; then
      echo "$SCHED" | grep -q '\[none\]'        && ok "$dev scheduler" "none"           || fail "$dev scheduler" "$SCHED" "none"
    elif [[ "$ROT" == "0"   ]]; then
      echo "$SCHED" | grep -q '\[mq-deadline\]' && ok "$dev scheduler" "mq-deadline"   || fail "$dev scheduler" "$SCHED" "mq-deadline"
    else
      echo "$SCHED" | grep -q '\[bfq\]'         && ok "$dev scheduler" "bfq"           || warn "$dev scheduler" "$SCHED" "bfq"
    fi
    (( RA <= 256 )) && ok "$dev read_ahead_kb" "${RA}" || warn "$dev read_ahead_kb" "${RA}" "<= 256"
  done
fi

# =============================================================================
_hdr "E. THP & KSM"
# =============================================================================

THP=$(file_val /sys/kernel/mm/transparent_hugepage/enabled)
THP_MODE=$(echo "$THP" | grep -o '\[[a-z+]*\]' | tr -d '[]')
[[ "$THP_MODE" == "madvise" ]] \
  && ok   "THP mode" "$THP_MODE" \
  || fail "THP mode" "$THP_MODE" "madvise"

DEFRAG=$(file_val /sys/kernel/mm/transparent_hugepage/defrag)
DEFRAG_MODE=$(echo "$DEFRAG" | grep -o '\[[a-z+]*\]' | tr -d '[]')
[[ "$DEFRAG_MODE" == "defer+madvise" ]] \
  && ok   "THP defrag" "$DEFRAG_MODE" \
  || fail "THP defrag" "$DEFRAG_MODE" "defer+madvise"

HP_1G=$(file_val /sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages 2>/dev/null || echo "0")
HP_2M=$(file_val /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages    2>/dev/null || echo "0")
inf "static hugepages: 1G=${HP_1G}  2M=${HP_2M}"
(( HP_1G > 0 || HP_2M > 0 )) \
  && ok   "static hugepages" "1G=${HP_1G} 2M=${HP_2M}" \
  || warn "static hugepages" "none" "> 0 if using hw:mem_page_size flavor"

KSM=$(file_val /sys/kernel/mm/ksm/run)
KSM_SCAN=$(file_val /sys/kernel/mm/ksm/pages_to_scan)
KSM_SLEEP=$(file_val /sys/kernel/mm/ksm/sleep_millisecs)
inf "KSM: pages_to_scan=${KSM_SCAN}  sleep_ms=${KSM_SLEEP}"
[[ "$KSM" == "1" ]] \
  && ok   "KSM enabled" "run=${KSM}" \
  || warn "KSM disabled" "run=${KSM}" "1"

SVC=$(systemctl is-active kvm-mem-tune.service 2>/dev/null || echo "not-found")
[[ "$SVC" == "active" ]] \
  && ok   "kvm-mem-tune.service" "active" \
  || warn "kvm-mem-tune.service" "$SVC" "active (THP/KSM may not survive reboots)"

# =============================================================================
_hdr "F. CGROUP CPU PRIORITY"
# =============================================================================

M_CPU=$(systemctl show machine.slice -p CPUWeight --value 2>/dev/null || echo "UNSET")
S_CPU=$(systemctl show system.slice  -p CPUWeight --value 2>/dev/null || echo "UNSET")
inf "machine.slice CPUWeight=${M_CPU}  system.slice CPUWeight=${S_CPU}"

if   [[ "$M_CPU" == "UNSET" ]];  then warn "machine.slice CPUWeight" "UNSET" "800"
elif (( M_CPU >= 800 ));          then ok   "machine.slice CPUWeight" "$M_CPU"
elif (( M_CPU >= 500 ));          then warn "machine.slice CPUWeight" "$M_CPU" "800 (acceptable but raise it)"
else                                   fail "machine.slice CPUWeight" "$M_CPU" ">= 800"
fi

[[ "$S_CPU" != "UNSET" ]] && (( S_CPU <= 100 )) \
  && ok   "system.slice CPUWeight" "$S_CPU" \
  || warn "system.slice CPUWeight" "$S_CPU" "<= 100"

CONF=/etc/systemd/system/machine.slice.d/priority.conf
[[ -r "$CONF" ]] \
  && ok   "machine.slice drop-in exists" "$CONF" \
  || warn "machine.slice drop-in missing" "not found" "$CONF (CPUWeight won't persist)"

# =============================================================================
_hdr "G. NOVA.CONF"
# =============================================================================

NOVA_CONF="/etc/nova/nova.conf"
if [[ ! -r "$NOVA_CONF" ]]; then
  warn "nova.conf" "not readable at $NOVA_CONF" "present"
else
  check_nova() {
    local label="$1" pattern="$2" want="$3"
    local val; val=$(grep -P "$pattern" "$NOVA_CONF" 2>/dev/null | head -1 | xargs || echo "")
    [[ -n "$val" ]] \
      && ok   "$label" "$val" \
      || fail "$label" "not set" "$want"
  }
  check_nova "virt_type"               "^\s*virt_type\s*="        "virt_type = kvm"
  check_nova "cpu_mode"                "^\s*cpu_mode\s*="         "cpu_mode = host-passthrough"
  check_nova "hw_machine_type"         "^\s*hw_machine_type\s*="  "hw_machine_type = x86_64=q35"
  check_nova "disk_cachemodes"         "^\s*disk_cachemodes\s*="  "disk_cachemodes = file=none,block=none"
  check_nova "rx_queue_size"           "^\s*rx_queue_size\s*="    "rx_queue_size = 1024"
  check_nova "tx_queue_size"           "^\s*tx_queue_size\s*="    "tx_queue_size = 1024"
  check_nova "cpu_model_extra_flags"   "^\s*cpu_model_extra_flags" "cpu_model_extra_flags = pcid"
fi

# =============================================================================
_hdr "H. QEMU.CONF"
# =============================================================================

QEMU_CONF="/etc/libvirt/qemu.conf"
if [[ ! -r "$QEMU_CONF" ]]; then
  warn "qemu.conf" "not readable at $QEMU_CONF" "present"
else
  check_qemu() {
    local label="$1" pattern="$2" want="$3"
    local val; val=$(grep -P "$pattern" "$QEMU_CONF" 2>/dev/null | head -1 | xargs || echo "")
    [[ -n "$val" ]] \
      && ok   "$label" "$val" \
      || warn "$label" "not set" "$want"
  }
  check_qemu "set_process_name" "^\s*set_process_name\s*=" "set_process_name = 1"
  check_qemu "max_processes"    "^\s*max_processes\s*="    "max_processes = 65536"
  check_qemu "max_files"        "^\s*max_files\s*="        "max_files = 65536"
fi

# =============================================================================
_hdr "I. IRQ AFFINITY"
# =============================================================================

IB=$(systemctl is-active irqbalance 2>/dev/null || echo "inactive")
if [[ -n "$(has_param "isolcpus")" ]]; then
  [[ "$IB" == "inactive" || "$IB" == "not-found" ]] \
    && ok   "irqbalance (isolcpus is set)" "inactive" \
    || warn "irqbalance active with isolcpus" "$IB" "inactive — set IRQBALANCE_BANNED_CPUS"
  BANNED=$(grep -oP 'IRQBALANCE_BANNED_CPUS=\S+' /etc/default/irqbalance 2>/dev/null || echo "")
  [[ -n "$BANNED" ]] \
    && ok   "IRQBALANCE_BANNED_CPUS" "$BANNED" \
    || warn "IRQBALANCE_BANNED_CPUS" "not set" "set to match isolcpus range"
else
  inf "isolcpus not set — irqbalance state: ${IB}"
fi

SVC=$(systemctl is-active irq-affinity.service 2>/dev/null || echo "not-found")
[[ "$SVC" == "active" ]] \
  && ok   "irq-affinity.service" "active" \
  || warn "irq-affinity.service" "$SVC" "active (manual IRQ pinning not applied)"

# vhost_net
lsmod | grep -q vhost_net \
  && ok   "vhost_net module" "loaded" \
  || warn "vhost_net module" "not loaded" "modprobe vhost_net"

# =============================================================================
# SUMMARY
# =============================================================================
TOTAL=$((PASS+WARN+FAIL))
echo -e "\n${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${X}"
echo -e "  ${G}[OK]  $PASS${X}   ${Y}[WARN] $WARN${X}   ${R}[FAIL] $FAIL${X}   total: $TOTAL"
echo ""
if   (( FAIL == 0 && WARN == 0 )); then echo -e "  ${G}${B}All tunings applied.${X}"
elif (( FAIL == 0 ));              then echo -e "  ${Y}${B}Warnings only — review items above.${X}"
else                                    echo -e "  ${R}${B}${FAIL} missing tuning(s) — apply sections above.${X}"; fi
echo ""