#!/usr/bin/env bash
set -euo pipefail

NOVA_CONF="${NOVA_CONF:-/opt/pf9/etc/nova/conf.d/nova_override.conf}"

FAILS=0

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RESET='\033[0m'
  BOLD='\033[1m'
  RED='\033[31m'
  GREEN='\033[32m'
  YELLOW='\033[33m'
  CYAN='\033[36m'
else
  RESET=''
  BOLD=''
  RED=''
  GREEN=''
  YELLOW=''
  CYAN=''
fi

section() { printf '\n%b== %s ==%b\n' "${BOLD}${CYAN}" "$*" "$RESET"; }
info()    { printf '%bINFO%b  %s\n' "$CYAN" "$RESET" "$*"; }
ok()      { printf '%bPASS%b  %s\n' "$GREEN" "$RESET" "$*"; }
warn()    { printf '%bWARN%b  %s\n' "$YELLOW" "$RESET" "$*"; }
bad()     { printf '%bFAIL%b  %s\n' "$RED" "$RESET" "$*"; FAILS=$((FAILS+1)); }

expand() {
  local IFS=,; local p
  for p in $1; do
    case "$p" in *-*) seq "${p%-*}" "${p#*-}" ;; "") ;; *) echo "$p" ;; esac
  done | sort -n
}
show_config() {
  local name="$1"
  local value="$2"

  if [ -n "$value" ]; then
    printf '%bSEEN%b      %s=%s\n' "$GREEN" "$RESET" "$name" "$value"
  else
    printf '%bNOT SEEN%b  %s\n' "$YELLOW" "$RESET" "$name"
  fi
}

section "Virtualization and KVM"
[ "$(grep -cE 'vmx|svm' /proc/cpuinfo)" -gt 0 ] && ok "CPU virt flags present" || bad "no vmx/svm flag"
[ -c /dev/kvm ] && ok "/dev/kvm present" || bad "/dev/kvm missing"
systemctl is-active --quiet libvirtd && ok "libvirtd active" || warn "libvirtd not active (check modular virtqemud)"

section "Kernel command line"
CMDLINE=$(cat /proc/cmdline)
echo "$CMDLINE" | grep -qE '(intel|amd)_iommu=on' && ok "IOMMU enabled on cmdline" || bad "no intel_iommu=on / amd_iommu=on"
echo "$CMDLINE" | grep -q 'iommu=pt'               && ok "iommu=pt"                 || warn "iommu=pt absent"
for k in isolcpus nohz_full rcu_nocbs; do
  echo "$CMDLINE" | grep -qE "${k}=[^ ]*" && ok "$k on cmdline" || bad "$k missing"
done
echo "$CMDLINE" | grep -qE "hugepagesz=|default_hugepagesz=" && ok "hugepage params on cmdline" || bad "no hugepage params"

section "CPU isolation (effective)"
ISOLATED_CPUS="$(cat /sys/devices/system/cpu/isolated 2>/dev/null || true)"
NOHZ_FULL_CPUS="$(cat /sys/devices/system/cpu/nohz_full 2>/dev/null || true)"
ONLINE_CPUS="$(cat /sys/devices/system/cpu/online)"

show_config "isolated CPUs" "$ISOLATED_CPUS"
show_config "nohz_full CPUs" "$NOHZ_FULL_CPUS"
show_config "online CPUs" "$ONLINE_CPUS"

section "SMT sibling pairing"
info "SMT active: $(cat /sys/devices/system/cpu/smt/active 2>/dev/null || echo n/a)"
for c in $(expand "$ISOLATED_CPUS"); do
  sib=$(cat /sys/devices/system/cpu/cpu"$c"/topology/thread_siblings_list)
  [ -z "$(comm -23 <(expand "$sib") <(expand "$ISOLATED_CPUS"))" ] ||
    warn "cpu$c sibling ($sib) outside isolated CPU set"
done
ok "SMT sibling check completed"

section "Current hugepage allocation"
grep -E \
  '^(HugePages_Total|HugePages_Free|HugePages_Rsvd|HugePages_Surp|Hugepagesize|Hugetlb):' \
  /proc/meminfo

findmnt -t hugetlbfs >/dev/null && ok "hugetlbfs mounted" || warn "no hugetlbfs mount"
if command -v virsh >/dev/null 2>&1; then
  info "NUMA hugepage allocation reported by virsh"
  virsh freepages --all || warn "virsh freepages --all failed"
else
  warn "virsh command unavailable"
fi

section "IRQ placement"
systemctl is-active --quiet irqbalance && ok "irqbalance active" || warn "irqbalance not active"
grep -E '^IRQBALANCE_BANNED_CPU' /etc/default/irqbalance || bad "no banned CPU setting in /etc/default/irqbalance"
HITS=0
for f in /proc/irq/[0-9]*/effective_affinity_list; do
  [ -r "$f" ] || continue
  if [ -n "$ISOLATED_CPUS" ] &&
    [ -n "$(comm -12 <(expand "$(cat "$f")") <(expand "$ISOLATED_CPUS"))" ]; then
    info "IRQ $(basename "$(dirname "$f")") is on isolated CPU set $(cat "$f")"
    HITS=$((HITS+1))
  fi
done

if [ "$HITS" -eq 0 ]; then
  ok "no IRQ effective-affinity on isolated CPUs"
else
  info "$HITS managed IRQ(s) have affinity on isolated CPUs"
fi

if [ -n "$ISOLATED_CPUS" ]; then
  ISOLATED_CPU_LIST="$(expand "$ISOLATED_CPUS" | paste -sd ' ' -)"
  info "Top processes and IRQ threads running on isolated CPUs"
  ps -eLo psr=,ppid=,pid=,comm= |
    awk -v list="$ISOLATED_CPU_LIST" \
      'BEGIN { n=split(list,a," "); for (i=1;i<=n;i++) s[a[i]]=1 } ($1 in s)' |
    sort |
    uniq -c |
    sort -rn |
    head -20 |
    awk '
      BEGIN {
        printf "%-7s %-6s %-8s %-8s %s\n", "COUNT", "CORE", "PPID", "PID", "PROCESS"
      }
      {
        printf "%-7s %-6s %-8s %-8s %s\n", $1, $2, $3, $4, $5
      }
    ' || true
else
  info "Process and IRQ thread mapping skipped because no isolated CPUs were detected"
fi

section "NIC passthrough configuration"
ls /sys/kernel/iommu_groups 2>/dev/null | grep -q . && ok "IOMMU groups exist" || bad "no IOMMU groups"

if command -v driverctl >/dev/null 2>&1; then
  info "Persistent driver overrides reported by driverctl"
  DRIVERCTL_OUTPUT="$(driverctl list-overrides 2>/dev/null || true)"

  if [ -n "$DRIVERCTL_OUTPUT" ]; then
    printf '%s\n' "$DRIVERCTL_OUTPUT"
  else
    printf '%bNOT SEEN%b  driverctl device overrides\n' "$YELLOW" "$RESET"
  fi

  VFIO_DEVICES="$(
    echo "$DRIVERCTL_OUTPUT" |
      awk '$2 == "vfio-pci" { print $1 }'
  )"

  if [ -n "$VFIO_DEVICES" ]; then
    info "Devices configured for vfio-pci passthrough"
    while IFS= read -r pci_bdf; do
      [ -n "$pci_bdf" ] || continue
      printf '%bPCI DEVICE%b  %s\n' "${BOLD}${CYAN}" "$RESET" "$pci_bdf"
      lspci -nnks "$pci_bdf" 2>/dev/null || warn "unable to query $pci_bdf with lspci"
    done <<< "$VFIO_DEVICES"
  else
    printf '%bNOT SEEN%b  vfio-pci driver overrides\n' "$YELLOW" "$RESET"
  fi
else
  warn "driverctl command unavailable"
fi

lsmod | grep -q '^vfio_pci' && ok "vfio_pci loaded" || warn "vfio_pci not loaded"

section "nova.conf"
val() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$NOVA_CONF" | tail -1; }
if [ -r "$NOVA_CONF" ]; then
  show_config "cpu_dedicated_set" "$(val cpu_dedicated_set)"
  show_config "cpu_shared_set" "$(val cpu_shared_set)"
  show_config "reserved_host_memory_mb" "$(val reserved_host_memory_mb)"

  grep -E '^[[:space:]]*(device_spec|alias|reserved_huge_pages)[[:space:]]*=' \
    "$NOVA_CONF" || printf '%bNOT SEEN%b  PCI aliases, device specs, or reserved hugepages\n' "$YELLOW" "$RESET"
else
  warn "$NOVA_CONF is not readable"
fi

section "Result"
if [ "$FAILS" -eq 0 ]; then
  ok "All mandatory checks passed"
else
  printf '%bFAIL%b  %s mandatory check(s) failed\n' "$RED" "$RESET" "$FAILS"
fi
exit "$FAILS"
