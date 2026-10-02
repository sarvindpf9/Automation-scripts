#!/usr/bin/env bash
set -euo pipefail

MARKER="/var/lib/firstboot/run"
SERVICE="firstboot-reset.service"
SERVICE2="firstboot-reset.path"
WAIT_SECONDS="${WAIT_SECONDS:-5}"

log(){ echo "[firstboot-reset] $*"; }

# Only run once if marker exists
if [[ ! -f "$MARKER" ]]; then
  log "Marker not present; exiting."
  exit 0
fi

log "Stopping network managers if present..."
if systemctl list-unit-files | grep -q '^NetworkManager.service'; then
  systemctl stop NetworkManager || true
fi
if systemctl list-unit-files | grep -q '^systemd-networkd.service'; then
  systemctl stop systemd-networkd || true
fi

log "Bringing all non-loopback interfaces down..."
for devpath in /sys/class/net/*; do
  dev="$(basename "$devpath")"
  [[ "$dev" == "lo" ]] && continue
  ip link set dev "$dev" down || true
done

log "Resetting machine-id and DBus machine-id..."
rm -f /etc/machine-id
dbus-uuidgen --ensure=/etc/machine-id
rm -f /var/lib/dbus/machine-id || true
dbus-uuidgen --ensure

# Print the newly generated machine-id from /etc/machine-id
MID="$(cat /etc/machine-id 2>/dev/null || true)"
log "New machine-id: ${MID}"

# Wait before disabling and rebooting
log "Waiting ${WAIT_SECONDS}s before disabling service and rebooting..."
sleep "${WAIT_SECONDS}"

log "Disabling service and removing marker so it never runs again..."
systemctl disable "$SERVICE" || true
systemctl disable "$SERVICE2" || true
rm -f "$MARKER"

sync
log "Rebooting now..."
reboot