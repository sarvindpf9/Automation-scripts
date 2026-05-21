#!/bin/bash
set -e  

echo "=== Ansible Collection Installation Script ==="
echo ""

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Installing latest yq packages..."
if ! command_exists yq; then
    wget -q https://github.com/mikefarah/yq/releases/download/v4.45.1/yq_linux_amd64
    sudo cp yq_linux_amd64 /usr/local/bin/yq
    sudo chmod +x /usr/local/bin/yq
    rm -rf yq_linux_amd64
    log "yq installed successfully"
else
    log "yq already installed, version: $(yq --version)"
fi

echo ""
log "Installing required python libraries..."

sudo apt-get update -qq
sudo apt-get install python3-venv python3-pip -y -qq

log "Installing ansible-core..."
pip3 install ansible-core

if [ -f "./ansible-collections-pf9/requirements.txt" ]; then
    log "Installing Python requirements from requirements.txt..."
    pip3 install -r ./ansible-collections-pf9/requirements.txt
else
    log "Warning: requirements.txt not found, skipping Python requirements installation"
fi

if [ -f "./ansible-collections-pf9/requirements.yml" ]; then
    log "Installing Ansible collection requirements from requirements.yml..."
    ansible-galaxy collection install -r ansible-collections-pf9/requirements.yml --force
else
    log "Warning: requirements.yml not found, skipping Ansible requirements installation"
fi

ANSIBLE_COLLECTIONS_DIR="$HOME/.ansible/collections"
log "Creating Ansible collections directory: $ANSIBLE_COLLECTIONS_DIR"
mkdir -p "$ANSIBLE_COLLECTIONS_DIR"

log "Building PF9 collection..."
if [ -d "./ansible-collections-pf9" ]; then
    ansible-galaxy collection build -v ./ansible-collections-pf9 --force
    
    PCD_COLLECTION_VERSION=$(cat ansible-collections-pf9/galaxy.yml | yq .version)
    log "Collection version: $PCD_COLLECTION_VERSION"
    
    COLLECTION_FILE="pf9-pcd-${PCD_COLLECTION_VERSION}.tar.gz"
    if [ -f "$COLLECTION_FILE" ]; then
        log "Installing PF9 collection to $ANSIBLE_COLLECTIONS_DIR..."
        ansible-galaxy collection install -v "./$COLLECTION_FILE" \
            -p "$ANSIBLE_COLLECTIONS_DIR" \
            --upgrade \
            --force
        
        rm -rf "$COLLECTION_FILE"
        log "Collection installed successfully and build file cleaned up"
    else
        log "Error: Collection build file $COLLECTION_FILE not found"
        exit 1
    fi
else
    log "Error: ansible-collections-pf9 directory not found"
    exit 1
fi

echo ""
log "=== Installation Complete ==="
log "Ansible collections installed to: $ANSIBLE_COLLECTIONS_DIR"

if command_exists ansible-galaxy; then
    echo ""
    log "Installed collections:"
    ansible-galaxy collection list --collections-path "$ANSIBLE_COLLECTIONS_DIR"
else
    log "Warning: ansible-galaxy command not found for verification"
fi

echo ""
log "Installation script completed successfully!"
