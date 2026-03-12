#!/usr/bin/env bash
set -euo pipefail

MARKER="/var/lib/firstboot/run"
SERVICE="firstboot-reset.service"
SERVICE2="firstboot-reset.path"
WAIT_SECONDS="${WAIT_SECONDS:-5}"

log(){ echo "[firstboot-reset] $*"; }

# ── Detect distro family ──────────────────────────────────────────────────────
detect_distro() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "${ID:-unknown}"
  else
    echo "unknown"
  fi
}
DISTRO="$(detect_distro)"
log "Detected distro: ${DISTRO}"

# Only run once — marker must exist
if [[ ! -f "$MARKER" ]]; then
  log "Marker not present; exiting."
  exit 0
fi

# ── Stop network managers ─────────────────────────────────────────────────────
log "Stopping network managers if present..."
for svc in NetworkManager systemd-networkd; do
  if systemctl list-unit-files --no-legend | awk '{print $1}' | grep -qx "${svc}.service"; then
    log "Stopping ${svc}..."
    systemctl stop "${svc}" || true
  fi
done

# ── Bring non-loopback interfaces down ───────────────────────────────────────
log "Bringing all non-loopback interfaces down..."
for devpath in /sys/class/net/*; do
  dev="$(basename "$devpath")"
  [[ "$dev" == "lo" ]] && continue
  ip link set dev "$dev" down 2>/dev/null || true
done

# ── Reset machine-id ──────────────────────────────────────────────────────────
# Rocky/RHEL: systemd-machine-id-setup is preferred; dbus-uuidgen may not exist
# Ubuntu:     both are typically present
log "Resetting machine-id..."
rm -f /etc/machine-id

if command -v systemd-machine-id-setup &>/dev/null; then
  # Preferred on all modern systemd distros; works on Rocky AND Ubuntu
  systemd-machine-id-setup
else
  # Fallback: dbus-uuidgen (may not be installed on minimal Rocky images)
  if command -v dbus-uuidgen &>/dev/null; then
    dbus-uuidgen --ensure=/etc/machine-id
  else
    # Last resort: generate via /proc/sys/kernel/random/uuid
    tr -d '-' < /proc/sys/kernel/random/uuid > /etc/machine-id
    chmod 444 /etc/machine-id
  fi
fi

# ── Reset DBus machine-id ─────────────────────────────────────────────────────
log "Resetting DBus machine-id..."
DBUS_ID_FILE="/var/lib/dbus/machine-id"
if [[ -e "$DBUS_ID_FILE" || -L "$DBUS_ID_FILE" ]]; then
  rm -f "$DBUS_ID_FILE"
fi

# On Rocky, /var/lib/dbus/ may not exist at all; create it if missing
mkdir -p /var/lib/dbus

if command -v dbus-uuidgen &>/dev/null; then
  dbus-uuidgen --ensure
else
  # Symlink to /etc/machine-id (systemd-recommended fallback)
  ln -sf /etc/machine-id "$DBUS_ID_FILE"
fi

MID="$(cat /etc/machine-id 2>/dev/null || true)"
log "New machine-id: ${MID}"

# ── Clear stale network config artefacts ──────────────────────────────────────
# Rocky (NetworkManager): remove persisted MAC/UUID lease state
if [[ "$DISTRO" =~ ^(rocky|rhel|centos|almalinux)$ ]]; then
  log "Removing Rocky/RHEL NM connection state..."
  rm -f /etc/NetworkManager/system-connections/*.nmconnection 2>/dev/null || true
  rm -rf /var/lib/NetworkManager/secret_key \
         /var/lib/NetworkManager/seen-bssids \
         /var/lib/NetworkManager/timestamps 2>/dev/null || true
fi

# Ubuntu (netplan / cloud-init): remove stale DHCP leases
if [[ "$DISTRO" =~ ^(ubuntu|debian)$ ]]; then
  log "Removing Ubuntu/Debian DHCP lease state..."
  rm -f /var/lib/dhcp/*.leases 2>/dev/null || true
  rm -f /run/systemd/netif/leases/* 2>/dev/null || true
fi

# ── Cloud-init cleanup (both distros if present) ──────────────────────────────
if command -v cloud-init &>/dev/null; then
  log "Cleaning cloud-init state..."
  cloud-init clean --logs --seed 2>/dev/null || true
fi

# ── Wait, disable, reboot ─────────────────────────────────────────────────────
log "Waiting ${WAIT_SECONDS}s before disabling service and rebooting..."
sleep "${WAIT_SECONDS}"

log "Disabling services and removing marker..."
systemctl disable "$SERVICE"  2>/dev/null || true
systemctl disable "$SERVICE2" 2>/dev/null || true
rm -f "$MARKER"

log "Rebooting..."
systemctl reboot