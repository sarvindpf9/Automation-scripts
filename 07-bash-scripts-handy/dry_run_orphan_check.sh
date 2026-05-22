#!/bin/bash
set -euo pipefail

# dry_run_orphan_check.sh
# Safe validation script for orphan multipath devices — NO DELETE ACTIONS

echo "===== ORPHAN MULTIPATH DRY RUN ====="
echo

orphans=(
  3600a098038314e65782b575176676d66
  3600a098038314e65782b575176676e55
  3600a098038314e65782b575176676e56
  3600a098038314e66303f575166593545
  3600a098038314e66303f575166593546
  3600a098038314e66303f57516659392d
  3600a098038314e66303f575166593941
  3600a098038314e66303f575166594132
)

for disk in "${orphans[@]}"; do
  echo "================================="
  echo "Checking: $disk"
  echo

  echo "[1] Multipath Details"
  multipath -ll "$disk" 2>/dev/null

  echo
  echo "[2] Mounted?"
  mount | grep "$disk" || true

  echo
  echo "[3] Process Using Device?"
  lsof "/dev/mapper/$disk" 2>/dev/null || true

  echo
  echo "[4] VM XML references"
  grep -R "$disk" /etc/libvirt/qemu/ 2>/dev/null || true

  echo
  echo "[5] Device Mapper info"
  dmsetup info | grep "$disk" || true

  echo
  echo "[6] lsblk"
  lsblk | grep "${disk:0:20}" || true

  echo
  echo "[7] OpenStack/Nova references"
  find /var/lib/nova -type f 2>/dev/null | xargs grep -l "$disk" 2>/dev/null || true

  echo
  echo "[8] Is filesystem present?"
  blkid | grep "$disk" || true

  echo
done

echo "===== DRY RUN COMPLETE ====="
