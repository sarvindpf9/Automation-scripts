#!/bin/bash
set -e

VENV_DIR=".venv-ansible"  # Name/location of your virtualenv
CONFIG_DIR="$HOME/.config/openstack"
CLOUDS_FILE="$CONFIG_DIR/clouds.yaml"

# If first arg is --remove-venv, clean up the virtual env safely and exit
if [ "$1" == "--remove-venv" ]; then
  echo "Requested removal of virtual environment at $VENV_DIR"

  if [ -d "$VENV_DIR" ]; then
    # Deactivate if currently active
    if [ -n "$VIRTUAL_ENV" ] && [ "$VIRTUAL_ENV" = "$(cd "$VENV_DIR"; pwd)" ]; then
      echo "Deactivating active virtualenv..."
      $VENV_DIR/bin/deactivate || true
    fi

    echo "Removing virtualenv directory $VENV_DIR..."
    rm -rf "$VENV_DIR"
    echo "Virtual environment removed."
  else
    echo "Virtual environment directory $VENV_DIR does not exist. Nothing to remove."
  fi

  exit 0
fi

# Arguments from user input for clouds.yaml config
AUTH_URL="$1"
USERNAME="$2"
PASSWORD="$3"
REGION_NAME="$4"

if [ -z "$AUTH_URL" ] || [ -z "$USERNAME" ] || [ -z "$PASSWORD" ] || [ -z "$REGION_NAME" ]; then
  echo "Usage:"
  echo "  $0 <auth_url> <username> <password> <region_name>"
  echo "  $0 --remove-venv     # to safely delete the Python virtualenv"
  exit 1
fi

echo "Install latest yq package.."
wget -q https://github.com/mikefarah/yq/releases/download/v4.45.1/yq_linux_amd64
sudo cp yq_linux_amd64 /usr/local/bin/yq
sudo chmod +x /usr/local/bin/yq
rm -rf yq_linux_amd64

echo ""
echo "Installing required Python tools.."
sudo apt-get update -qq
sudo apt-get install python3-venv python3-pip -y -qq

echo ""
echo "Setting up Python virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "Activating virtualenv.."
source "$VENV_DIR/bin/activate"

echo "Upgrading pip.."
pip install --upgrade pip

echo "Installing Ansible core and dependencies.."
pip install ansible-core
pip install -r ./ansible-collections-pf9/requirements.txt

echo ""
echo "Installing Ansible collections.."
ansible-galaxy collection install -r ansible-collections-pf9/requirements.yml --force
ansible-galaxy collection build -v ./ansible-collections-pf9 --force

echo "Installing latest OpenStack client..."
pip install python-openstackclient

P9_VERSION=$(cat ansible-collections-pf9/galaxy.yml | yq .version)

ansible-galaxy collection install -v "./pf9-pcd-${P9_VERSION}.tar.gz" -p ./collections --upgrade
rm -rf "pf9-pcd-${P9_VERSION}.tar.gz"

echo ""
echo "Creating OpenStack config directory and clouds.yaml.."
mkdir -p "$CONFIG_DIR"

cat > "$CLOUDS_FILE" <<EOL
clouds:
  $REGION_NAME:
    auth:
      auth_url: $AUTH_URL/keystone/v3
      project_name: service
      username: $USERNAME
      password: $PASSWORD
      user_domain_name: default
      project_domain_name: default
    region_name: $REGION_NAME
    interface: public
    identity_api_version: 3
    compute_api_version: 2
    volume_api_version: 3
    image_api_version: 2
    identity_interface: public
    volume_interface: public
EOL

echo ""
echo "OpenStack clouds.yaml created at $CLOUDS_FILE"
echo ""
echo "Setup complete."
echo ""
echo "To use this environment in the future or CI/CD jobs, activate the virtualenv:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "To safely remove this virtualenv later, run:"
echo "    $0 --remove-venv"
