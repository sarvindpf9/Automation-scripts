#!/bin/bash
FILENAME="/opt/pf9/etc/nova/conf.d/nova_override.conf"
SERVICE="pf9-ostackhost"

# Backup the file to /tmp with timestamp
BACKUP="/tmp/nova_override.conf.$(date +%Y%m%d_%H%M%S).bak"
cp "$FILENAME" "$BACKUP"
echo "Backup created at $BACKUP"

if grep -q '^\[DEFAULT\]' "$FILENAME"; then
  grep -q '^running_deleted_instance_action = reap' "$FILENAME" || {
    sed -i '/^\[DEFAULT\]/a running_deleted_instance_action = reap' "$FILENAME" && \
    sudo systemctl restart "$SERVICE" && \
    echo "Service status:" && systemctl status "$SERVICE" | grep Active
  }
else
  printf "\n[DEFAULT]\nrunning_deleted_instance_action = reap\n" >> "$FILENAME" && \
  sudo systemctl restart "$SERVICE" && \
  echo "Service status:" && systemctl status "$SERVICE" | grep Active
fi

grep -A3 '^\[DEFAULT\]' "$FILENAME"
