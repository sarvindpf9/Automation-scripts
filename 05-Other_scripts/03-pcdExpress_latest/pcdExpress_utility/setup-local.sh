#!/bin/bash

# install yq packages:
echo "Install latest yq packages.."
wget -q https://github.com/mikefarah/yq/releases/download/v4.45.1/yq_linux_amd64
sudo cp yq_linux_amd64 /usr/local/bin/yq
sudo chmod +x /usr/local/bin/yq
rm -rf yq_linux_amd64

echo ""

echo "Installing required python libraries.."
sudo apt-get install python3-venv python3-pip -y -qq
pip3 install ansible-core
pip3 install -r ./ansible-collections-pf9/requirements.txt
ansible-galaxy collection install -r ansible-collections-pf9/requirements.yml --force
ansible-galaxy collection build -v ./ansible-collections-pf9 --force
PCD_COLLECTION_VERSION=$(cat ansible-collections-pf9/galaxy.yml| yq .version)

# install pf9 collections:
ansible-galaxy collection install -v ./pf9-pcd-${PCD_COLLECTION_VERSION}.tar.gz -p ./collections --upgrade
rm -rf pf9-pcd-${PCD_COLLECTION_VERSION}.tar.gz
