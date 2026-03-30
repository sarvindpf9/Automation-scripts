#!/usr/bin/env bash
# =============================================================================
# kvm_nova_tuning_audit.sh
# Audits KVM/Nova compute host tuning state on Ubuntu 22.04
# Works with both linux-generic and linux-lowlatency kernels
# Run as root. Output: console + optional log file.
# =============================================================================

set -euo pipefail

LOG_FILE="${1:-}"
PASS=0; WARN=0; FAIL=0

# ── colour ────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'; YLW='\033[0;33m'; GRN='\033[0;32m'
  CYN='\033[0;36m'; BLD='\033[1m';    RST='\033[0m'
else
  RED=''; YLW=''; GRN=''; CYN=''; BLD=''; RST=''
fi

_out() { echo -e "$*"; [[ -n "$LOG_FILE" ]] && echo -e "$*" >> "$LOG_FILE"; }

ok()   { _out "  ${GRN}[OK]${RST}   $*";   ((PASS++));  }
warn() { _out "  ${YLW}[WARN]${RST} $*";   ((WARN++));  }
fail() { _out "  ${RED}[FAIL]${RST} $*";   ((FAIL++));  }
info() { _out "  ${CYN}[INFO]${RST} $*";              }
hdr()  { _out "\n${BLD}━━━ $* ━━━${RST}";             }
val()  { _out "         current : ${CYN}$1${RST}  →  expected: ${BLD}$2${RST}"; }

# ── helpers ───────────────────────────────────────────────────────────────────
sysctl_get() { sysctl -n "$1" 2>/dev/null || echo "UNSET"; }
file_get()   { [[ -r "$1" ]] && cat "$1" || echo "UNREAD"; }
cmdline()    { grep -o "$1" /proc/cmdline 2>/dev/null || echo ""; }
kconfig()    { grep "^$1=" "/boot/config-$(uname -r)" 2>/dev/null | cut -d= -f2 || echo "NOT_SET"; }

check_sysctl() {
  local key="$1" expected="$2" label="${3:-$1}"
  local cur; cur=$(sysctl_get "$key")
  val "$cur" "$expected"
  if [[ "$cur" == "$expected" ]]; then ok "$label"; else fail "$label"; fi
}

check_sysctl_ge() {
  local key="$1" min="$2" label="${3:-$1}"
  local cur; cur=$(sysctl_get "$key")
  val "$cur" ">= $min"
  if [[ "$cur" != "UNSET" ]] && (( cur >= min )); then ok "$label"; else fail "$label"; fi
}

check_sysctl_le() {
  local key="$1" max="$2" label="${3:-$1}"
  local cur; cur=$(sysctl_get "$key")
  val "$cur" "<= $max"
  if [[ "$cur" != "UNSET" ]] && (( cur <= max )); then ok "$label"; else fail "$label"; fi
}

# =============================================================================
_out ""
_out "${BLD}╔══════════════════════════════════════════════════════════════╗${RST}"
_out "${BLD}║     KVM / Nova Compute Tuning Audit — Ubuntu 22.04           ║${RST}"
_out "${BLD}╚══════════════════════════════════════════════════════════════╝${RST}"
_out "  Host    : $(hostname)"
_out "  Date    : $(date)"
_out "  Kernel  : $(uname -r)"
_out "  User    : $(whoami)"
if [[ $EUID -ne 0 ]]; then
  warn "Not running as root — some checks may be incomplete"; fi

# =============================================================================
hdr "1. KERNEL VARIANT"
# =============================================================================

KVER=$(uname -r)
IS_LL=0; IS_HWE=0
[[ "$KVER" == *lowlatency* ]] && IS_LL=1
[[ "$KVER" == *-hwe*       ]] && IS_HWE=1

val "$KVER" "5.15.x-lowlatency (recommended)"
if   [[ $IS_LL -eq 1 ]]; then ok  "linux-lowlatency kernel active"
elif [[ $IS_HWE -eq 1 ]]; then warn "HWE generic kernel — install linux-lowlatency-hwe-22.04"
else                           warn "GA generic kernel — HZ=250, PREEMPT_DYNAMIC (suboptimal for KVM)"; fi

HZ=$(kconfig "CONFIG_HZ")
val "$HZ" "1000"
if [[ "$HZ" == "1000" ]]; then ok "HZ=1000 (1ms ticks)"; else fail "HZ=${HZ} — VM timer jitter (1000 requires lowlatency)"; fi

PREE=$(kconfig "CONFIG_PREEMPT")
PREEDYN=$(kconfig "CONFIG_PREEMPT_DYNAMIC")
val "${PREE:-PREEMPT_DYNAMIC}" "y (full preemption)"
if [[ "$PREE" == "y" ]]; then ok "CONFIG_PREEMPT=y (full, compiled-in)"
elif [[ "$PREEDYN" == "y" ]]; then
  RUNTIME=$(file_get /sys/kernel/debug/sched/preempt 2>/dev/null || cmdline "preempt=full")
  if [[ "$RUNTIME" == *full* ]]; then warn "PREEMPT_DYNAMIC — runtime set to full (partial fix; CONFIG_PREEMPT=y is better)"
  else fail "PREEMPT_DYNAMIC — not shifted to full (add preempt=full to cmdline)"; fi
fi

# =============================================================================
hdr "2. CPU — GOVERNOR & FREQUENCY"
# =============================================================================

CPU0_GOV=$(file_get /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
val "$CPU0_GOV" "performance"
if [[ "$CPU0_GOV" == "performance" ]]; then ok "cpufreq governor = performance (cpu0)"
else fail "cpufreq governor = ${CPU0_GOV} (expected: performance)"; fi

MISMATCHED=0
for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  g=$(cat "$f"); [[ "$g" != "performance" ]] && MISMATCHED=$((MISMATCHED+1))
done
val "$MISMATCHED cores not on performance" "0"
if (( MISMATCHED == 0 )); then ok "All CPU cores on performance governor"
else fail "$MISMATCHED CPU core(s) not on performance governor"; fi

DRIVER=$(file_get /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver)
val "$DRIVER" "amd_pstate_epp or acpi-cpufreq"
info "cpufreq driver: ${CYN}${DRIVER}${RST}"

if [[ -r /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference ]]; then
  EPP=$(file_get /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference)
  val "$EPP" "performance"
  if [[ "$EPP" == "performance" ]]; then ok "EPP (energy_performance_preference) = performance"
  else warn "EPP = ${EPP} (set to performance for amd_pstate_epp driver)"; fi
else info "EPP not available (not amd_pstate_epp driver — OK)"; fi

MAX_CSTATE=$(cmdline "processor.max_cstate=[0-9]*" | grep -o '[0-9]*' || echo "")
val "${MAX_CSTATE:-not set}" "1"
if [[ "$MAX_CSTATE" == "1" ]]; then ok "processor.max_cstate=1 in cmdline"
else warn "processor.max_cstate not set to 1 — C-state latency may affect VM IRQ delivery"; fi

AMD_PSTATE=$(cmdline "amd_pstate=[a-z]*" | grep -o '=.*' | tr -d '=' || echo "")
val "${AMD_PSTATE:-not set}" "passive or active"
if [[ -n "$AMD_PSTATE" ]]; then ok "amd_pstate=${AMD_PSTATE} in cmdline"
else info "amd_pstate not in cmdline (may be fine if using acpi-cpufreq)"; fi

# =============================================================================
hdr "3. CPU — ISOLATION & SCHEDULING"
# =============================================================================

ISOLCPUS=$(cmdline "isolcpus=[^ ]*" | sed 's/isolcpus=//' || echo "")
val "${ISOLCPUS:-not set}" "e.g. nohz,domain,4-N"
if [[ -n "$ISOLCPUS" ]]; then ok "isolcpus set: ${ISOLCPUS}"
else warn "isolcpus not set — host scheduler can interfere with VM vCPU threads"; fi

NOHZ=$(cmdline "nohz_full=[^ ]*" | sed 's/nohz_full=//' || echo "")
val "${NOHZ:-not set}" "same range as isolcpus"
if [[ -n "$NOHZ" ]]; then ok "nohz_full set: ${NOHZ}"
else warn "nohz_full not set"; fi

RCU=$(cmdline "rcu_nocbs=[^ ]*" | sed 's/rcu_nocbs=//' || echo "")
val "${RCU:-not set}" "same range as isolcpus"
if [[ -n "$RCU" ]]; then ok "rcu_nocbs set: ${RCU}"
else warn "rcu_nocbs not set — RCU callbacks may interfere with isolated vCPU cores"; fi

SKEW=$(cmdline "skew_tick=1" || echo "")
val "${SKEW:-not set}" "skew_tick=1"
if [[ -n "$SKEW" ]]; then ok "skew_tick=1 in cmdline"
else warn "skew_tick=1 not set — timer tick spreading not enabled"; fi

# cgroup CPU weight
MACHINE_CPU=$(systemctl show machine.slice -p CPUWeight --value 2>/dev/null || echo "UNSET")
val "$MACHINE_CPU" ">= 500"
if [[ "$MACHINE_CPU" != "UNSET" ]] && (( MACHINE_CPU >= 500 )); then ok "machine.slice CPUWeight=${MACHINE_CPU}"
else warn "machine.slice CPUWeight=${MACHINE_CPU} (recommended >= 500 for VM priority)"; fi

# =============================================================================
hdr "4. MEMORY"
# =============================================================================

check_sysctl "vm.overcommit_memory" "1" "vm.overcommit_memory"
check_sysctl_le "vm.swappiness" "10" "vm.swappiness"
check_sysctl_le "vm.vfs_cache_pressure" "50" "vm.vfs_cache_pressure"
check_sysctl "vm.compaction_proactiveness" "0" "vm.compaction_proactiveness"
check_sysctl "kernel.numa_balancing" "0" "kernel.numa_balancing"

THP=$(file_get /sys/kernel/mm/transparent_hugepage/enabled)
val "$THP" "[madvise] or [always]"
if echo "$THP" | grep -q '\[madvise\]\|\[always\]'; then ok "THP enabled (mode: $(echo $THP | grep -o '\[[a-z]*\]'))"
else warn "THP = ${THP} (recommend madvise for KVM)"; fi

THP_DEFRAG=$(file_get /sys/kernel/mm/transparent_hugepage/defrag)
val "$THP_DEFRAG" "[defer+madvise]"
if echo "$THP_DEFRAG" | grep -q '\[defer+madvise\]'; then ok "THP defrag = defer+madvise"
else warn "THP defrag = ${THP_DEFRAG} (recommend defer+madvise to avoid compaction stalls)"; fi

HP_1G=$(file_get /sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages 2>/dev/null || echo "0")
HP_2M=$(file_get /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages 2>/dev/null || echo "0")
val "1G=${HP_1G}  2M=${HP_2M}" "> 0 (if using static hugepages)"
if (( HP_1G > 0 )); then ok "Static 1G hugepages allocated: ${HP_1G}"
elif (( HP_2M > 0 )); then ok "Static 2M hugepages allocated: ${HP_2M}"
else warn "No static hugepages allocated (THP-only; acceptable if not using hw:mem_page_size flavor)"; fi

KSM=$(file_get /sys/kernel/mm/ksm/run)
val "$KSM" "1"
if [[ "$KSM" == "1" ]]; then
  KSM_SCAN=$(file_get /sys/kernel/mm/ksm/pages_to_scan)
  KSM_SLEEP=$(file_get /sys/kernel/mm/ksm/sleep_millisecs)
  ok "KSM enabled (pages_to_scan=${KSM_SCAN}, sleep_ms=${KSM_SLEEP})"
else warn "KSM disabled — PVE enables this by default for memory density"; fi

# =============================================================================
hdr "5. STORAGE I/O"
# =============================================================================

for dev in $(lsblk -d -n -o NAME,TYPE | awk '$2=="disk"{print $1}'); do
  SCHED=$(file_get /sys/block/${dev}/queue/scheduler)
  ROT=$(file_get /sys/block/${dev}/queue/rotational)
  NR=$(file_get /sys/block/${dev}/queue/nr_requests)
  RA=$(file_get /sys/block/${dev}/queue/read_ahead_kb)
  info "Block device: ${dev}  rotational=${ROT}  nr_requests=${NR}  read_ahead_kb=${RA}"
  val "$SCHED" "none (nvme) or mq-deadline (ssd) or bfq (hdd)"
  if [[ "$dev" == nvme* ]]; then
    if echo "$SCHED" | grep -q '\[none\]'; then ok "${dev}: scheduler=none (correct for NVMe)"
    else fail "${dev}: scheduler=${SCHED} (NVMe should use none)"; fi
  elif [[ "$ROT" == "0" ]]; then
    if echo "$SCHED" | grep -q '\[mq-deadline\]'; then ok "${dev}: scheduler=mq-deadline (correct for SSD)"
    else fail "${dev}: scheduler=${SCHED} (SSD should use mq-deadline)"; fi
  else
    if echo "$SCHED" | grep -q '\[bfq\]'; then ok "${dev}: scheduler=bfq (correct for HDD)"
    else warn "${dev}: scheduler=${SCHED} (HDD recommend bfq)"; fi
  fi
done

AIO_MAX=$(sysctl_get "fs.aio_max_nr")
val "$AIO_MAX" ">= 1048576"
if (( AIO_MAX >= 1048576 )); then ok "fs.aio_max_nr=${AIO_MAX}"
else fail "fs.aio_max_nr=${AIO_MAX} — too low for io_uring under heavy VM I/O"; fi

# =============================================================================
hdr "6. NETWORK STACK"
# =============================================================================

check_sysctl_ge "net.core.rmem_max" "134217728" "net.core.rmem_max"
check_sysctl_ge "net.core.wmem_max" "134217728" "net.core.wmem_max"
check_sysctl_ge "net.core.netdev_max_backlog" "5000" "net.core.netdev_max_backlog"
check_sysctl_ge "net.core.somaxconn" "4096" "net.core.somaxconn"

TCP_CC=$(sysctl_get "net.ipv4.tcp_congestion_control")
val "$TCP_CC" "bbr"
if [[ "$TCP_CC" == "bbr" ]]; then ok "TCP congestion control = bbr"
else warn "TCP congestion control = ${TCP_CC} (recommend bbr)"; fi

QDISC=$(sysctl_get "net.core.default_qdisc")
val "$QDISC" "fq"
if [[ "$QDISC" == "fq" ]]; then ok "default_qdisc = fq"
else warn "default_qdisc = ${QDISC} (recommend fq for bbr)"; fi

IRQBAL=$(systemctl is-active irqbalance 2>/dev/null || echo "inactive")
val "$IRQBAL" "inactive (if using manual IRQ pinning)"
if [[ "$IRQBAL" == "inactive" ]]; then ok "irqbalance inactive (manual IRQ control)"
elif [[ -n "$ISOLCPUS" ]]; then warn "irqbalance active with isolcpus set — verify IRQBALANCE_BANNED_CPUS excludes isolated cores"
else info "irqbalance active (acceptable if not doing manual IRQ pinning)"; fi

# =============================================================================
hdr "7. KERNEL SCHEDULER TUNABLES"
# =============================================================================

check_sysctl_le "kernel.sched_min_granularity_ns"  "4000000" "sched_min_granularity_ns"
check_sysctl_le "kernel.sched_wakeup_granularity_ns" "2000000" "sched_wakeup_granularity_ns"
check_sysctl_ge "kernel.sched_migration_cost_ns"   "3000000" "sched_migration_cost_ns"

WATCHDOG=$(sysctl_get "kernel.watchdog")
val "$WATCHDOG" "0"
if [[ "$WATCHDOG" == "0" ]]; then ok "kernel.watchdog=0 (no spurious soft lockup noise)"
else warn "kernel.watchdog=1 — on a busy compute host this can produce false softlockup warnings"; fi

# =============================================================================
hdr "8. SERVICES (libvirt / QEMU / Nova)"
# =============================================================================

for svc in libvirtd nova-compute; do
  STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
  val "$STATUS" "active"
  if [[ "$STATUS" == "active" ]]; then ok "${svc} is active"
  elif [[ "$STATUS" == "not-found" ]]; then info "${svc} not installed (skip)"
  else fail "${svc} is ${STATUS}"; fi
done

QEMU_VER=$(qemu-system-x86_64 --version 2>/dev/null | head -1 || echo "not found")
val "$QEMU_VER" "QEMU >= 6.2"
info "QEMU: ${CYN}${QEMU_VER}${RST}"
if echo "$QEMU_VER" | grep -qE 'version [7-9]|version [1-9][0-9]'; then ok "QEMU 7+ (good — ubuntu-cloud-archive version)"
elif echo "$QEMU_VER" | grep -q 'version 6'; then warn "QEMU 6.x — functional but older; consider ubuntu-cloud-archive for newer build"
else fail "QEMU not found or very old"; fi

LIBVIRT_VER=$(virsh version --daemon 2>/dev/null | grep "^Compiled" | awk '{print $NF}' || echo "unknown")
info "libvirt daemon version: ${CYN}${LIBVIRT_VER}${RST}"

# libvirt qemu.conf checks
QEMU_CONF="/etc/libvirt/qemu.conf"
if [[ -r "$QEMU_CONF" ]]; then
  for param in "set_process_name = 1" "max_processes" "max_files"; do
    if grep -q "$param" "$QEMU_CONF" 2>/dev/null; then ok "qemu.conf: ${param} set"
    else warn "qemu.conf: ${param} not found — check ${QEMU_CONF}"; fi
  done
else warn "qemu.conf not readable at ${QEMU_CONF}"; fi

# nova.conf checks
NOVA_CONF="/etc/nova/nova.conf"
if [[ -r "$NOVA_CONF" ]]; then
  for param in "virt_type = kvm" "cpu_mode" "disk_cachemodes" "rx_queue_size" "tx_queue_size"; do
    if grep -q "$param" "$NOVA_CONF" 2>/dev/null; then ok "nova.conf: ${param} set"
    else warn "nova.conf: ${param} not found — check ${NOVA_CONF}"; fi
  done
else warn "nova.conf not readable at ${NOVA_CONF}"; fi

# =============================================================================
hdr "9. POTENTIAL ISSUES WITH linux-lowlatency"
# =============================================================================

if [[ $IS_LL -eq 1 ]]; then
  info "linux-lowlatency kernel detected — checking known risk areas"

  # DKMS modules
  if command -v dkms &>/dev/null; then
    DKMS_OUT=$(dkms status 2>/dev/null || echo "")
    if [[ -n "$DKMS_OUT" ]]; then
      info "DKMS modules found:"
      while IFS= read -r line; do info "  $line"; done <<< "$DKMS_OUT"
      BROKEN=$(echo "$DKMS_OUT" | grep -v "installed" | grep -v "^$" || true)
      if [[ -n "$BROKEN" ]]; then fail "Some DKMS modules NOT built for current lowlatency kernel — run: dkms autoinstall"
      else ok "All DKMS modules installed for lowlatency kernel"; fi
    else ok "No DKMS modules found (nothing to rebuild)"; fi
  else info "dkms not installed — no out-of-tree module check needed"; fi

  # OVS-DPDK check
  if systemctl is-active openvswitch-switch &>/dev/null; then
    if grep -r "dpdk" /etc/openvswitch/ /etc/default/openvswitch* 2>/dev/null | grep -qi "dpdk\|pmd"; then
      fail "OVS-DPDK appears configured — full preemption can interfere with poll-mode workers. Test under load."
    else ok "OVS present but no DPDK poll-mode config detected"; fi
  else info "openvswitch-switch not active (no OVS-DPDK risk)"; fi

  # Mixed-fleet detection
  if command -v openstack &>/dev/null; then
    MIXED=$(openstack compute service list -f value -c Host -c State 2>/dev/null \
      | awk '{print $1}' | sort -u \
      | xargs -I{} ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 {} uname -r 2>/dev/null \
      | sort -u | wc -l || echo "0")
    if (( MIXED > 1 )); then warn "Detected mixed kernel versions across compute nodes — live migration between different kernel types carries risk. Roll out lowlatency to all nodes."
    else info "Fleet kernel check: uniform (or SSH not available for remote check)"; fi
  else info "openstack CLI not available — cannot check fleet kernel homogeneity"; fi

  # thermald / PPD conflict
  for svc in thermald power-profiles-daemon; do
    S=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
    if [[ "$S" == "active" ]]; then
      fail "${svc} is active — conflicts with manual cpufreq governor setting on lowlatency kernel. Disable it."
    else ok "${svc} inactive (no governor conflict)"; fi
  done

  # Hugepage compaction on lowlatency
  COMP=$(sysctl_get "vm.compaction_proactiveness")
  if [[ "$COMP" == "0" ]]; then ok "vm.compaction_proactiveness=0 (prevents compaction stalls on lowlatency)"
  else warn "vm.compaction_proactiveness=${COMP} — set to 0 on lowlatency to avoid THP compaction stalls during VM hugepage alloc"; fi

else
  info "Running generic kernel — lowlatency-specific checks skipped"
  warn "Consider: apt install linux-lowlatency-hwe-22.04  (HZ=1000, CONFIG_PREEMPT=y)"
fi

# =============================================================================
hdr "10. GRUB CMDLINE SNAPSHOT"
# =============================================================================

CMDLINE=$(cat /proc/cmdline)
info "Full cmdline: ${CYN}${CMDLINE}${RST}"

for param in "processor.max_cstate" "preempt" "isolcpus" "nohz_full" "rcu_nocbs" "transparent_hugepage" "skew_tick"; do
  FOUND=$(echo "$CMDLINE" | grep -o "${param}=[^ ]*" || echo "")
  if [[ -n "$FOUND" ]]; then ok "cmdline: ${FOUND}"
  else warn "cmdline: ${param} not set"; fi
done

# =============================================================================
hdr "SUMMARY"
# =============================================================================

TOTAL=$((PASS + WARN + FAIL))
_out ""
_out "  ${GRN}[OK]  ${PASS}${RST}   ${YLW}[WARN]  ${WARN}${RST}   ${RED}[FAIL]  ${FAIL}${RST}   Total: ${TOTAL}"
_out ""
if   (( FAIL == 0 && WARN == 0 )); then _out "  ${GRN}${BLD}Host is fully tuned — PVE-equivalent configuration.${RST}"
elif (( FAIL == 0 ));               then _out "  ${YLW}${BLD}Host partially tuned — address warnings above for full performance.${RST}"
else                                     _out "  ${RED}${BLD}Host has critical gaps — address FAIL items before production use.${RST}"; fi
_out ""
[[ -n "$LOG_FILE" ]] && _out "  Full log written to: ${LOG_FILE}"