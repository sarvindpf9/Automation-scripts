#!/bin/bash

# Exit on any error
set -euo pipefail

echo "Installing dependent packages..."
echo "==============================="

# Make package installs non-interactive
export DEBIAN_FRONTEND=noninteractive

# Update APT cache
sudo apt-get update -qq

# Install required packages silently
sudo apt-get install -y -qq \
    ssvnc \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    qemu-system \
    qemu-utils \
    ovmf \
    swtpm \
    cloud-image-utils \
    xorriso \
    libnbd-bin \
    nbdkit \
    wimtools \
    fuse2fs \
    git \
    jq \
    unzip

echo ""

# Ensure user is part of 'kvm' group
if getent group kvm > /dev/null 2>&1; then
    if id -nG "$USER" | grep -qw kvm; then
        echo "User '$USER' is already a member of the 'kvm' group."
    else
        echo "Adding user '$USER' to the 'kvm' group..."
        sudo usermod -aG kvm "$USER"
    fi
else
    echo "Error: 'kvm' group does not exist. Ensure virtualization is enabled and kvm is installed."
    exit 1
fi

if [ ! -e /dev/kvm ]; then
    echo "Warning: /dev/kvm not found. Nested virtualisation may not be enabled — QEMU builds will run without KVM acceleration."
fi

echo ""

OVMF_VARS_SRC="/usr/share/OVMF/OVMF_VARS_4M.fd"
OVMF_VARS_LOCAL="$(dirname "$0")/ovmf-vars.fd"
if [ -f "$OVMF_VARS_SRC" ]; then
    echo "Copying OVMF_VARS to build-local ovmf-vars.fd..."
    cp "$OVMF_VARS_SRC" "$OVMF_VARS_LOCAL"
    chmod 644 "$OVMF_VARS_LOCAL"
else
    echo "Error: $OVMF_VARS_SRC does not exist. Is the 'ovmf' package installed?"
    exit 1
fi

echo ""

# Install Packer from official HashiCorp APT repo if not present
if ! command -v packer >/dev/null 2>&1; then
    echo "Installing Packer from official HashiCorp repository..."

    # Add HashiCorp GPG key
    curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/hashicorp.gpg

    # Add HashiCorp repo if not already added
    if ! grep -q "apt.releases.hashicorp.com" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
        echo "Adding HashiCorp APT repository..."
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/trusted.gpg.d/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
            sudo tee /etc/apt/sources.list.d/hashicorp.list > /dev/null
    fi

    # Update and install packer
    sudo apt-get update -qq
    sudo apt-get install -y -qq packer
else
    echo "Packer is already installed. Skipping installation."
fi

echo ""
echo "======================================"
echo "Preflight package installation complete."
echo -e "\033[0;31mPlease log out and log back in for group changes to take effect.\033[0m"

