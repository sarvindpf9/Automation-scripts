#!/usr/bin/env bash
# Usage: sudo ./create_pwless_sudo_user.sh <username>
# EMBEDDED PUBLIC KEY - place your public key in this variable

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <username>"
    exit 1
fi

USER_NAME="$1"

# Replace with YOUR actual public key (ssh-ed25519/id_rsa.pub content)
EMBEDDED_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDaIU8nUWie2zHO+rw/ybmLgMMk7h+cAQuCaZ27T2qKE ubuntu@ubuntu-desktop-proxsa"

# Must be run as root
if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root (sudo)." >&2
    exit 1
fi

# Validate Ubuntu sudo group
if ! getent group sudo >/dev/null; then
    echo "Ubuntu 'sudo' group required." >&2
    exit 1
fi

# User handling
if ! id "$USER_NAME" &>/dev/null; then
    useradd -m -s /bin/bash "$USER_NAME"
    echo "Created '$USER_NAME'."
else
    echo "Using existing '$USER_NAME'."
fi

# Sudo group (idempotent)
if ! groups "$USER_NAME" | grep -qw sudo; then
    usermod -aG sudo "$USER_NAME"
    echo "Added to sudo group."
fi

# Passwordless sudo
SUDOERS_FILE="/etc/sudoers.d/${USER_NAME}"
echo "${USER_NAME} ALL=(ALL) NOPASSWD: ALL" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
if command -v visudo >/dev/null && ! visudo -cf "$SUDOERS_FILE"; then
    echo "Sudoers error." >&2
    rm "$SUDOERS_FILE"
    exit 1
fi
echo "Passwordless sudo configured."

# SSH KEY SETUP with EMBEDDED KEY
SSH_DIR="/home/${USER_NAME}/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

mkdir -p "$SSH_DIR"
chown "${USER_NAME}:${USER_NAME}" "$SSH_DIR"
chmod 700 "$SSH_DIR"

# Use embedded key (always)
if [[ -z "$EMBEDDED_PUBKEY" || "$EMBEDDED_PUBKEY" == "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... your-email@example.com" ]]; then
    echo "UPDATE REQUIRED: Replace EMBEDDED_PUBKEY with your actual public key!" >&2
    exit 1
fi

# Append embedded key if not present
if ! grep -F "$EMBEDDED_PUBKEY" "$AUTH_KEYS" >/dev/null 2>&1; then
    echo "$EMBEDDED_PUBKEY" >> "$AUTH_KEYS"
    echo "SSH key added."
else
    echo "key already exists."
fi

chown "${USER_NAME}:${USER_NAME}" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

echo
echo "'$USER_NAME' READY WITH EMBEDDED ACCESS!"
echo "- Passwordless sudo set"
echo "- SSH key added successfully"