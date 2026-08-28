#!/bin/bash
set -e

# Install pip package
sudo apt install python3.12-venv -y

# Setup only virtualenv.. nothing else
VENV_DIR=".venv-local"  # Name/location of your virtualenv

echo ""
echo "Setting up Python virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "Activating virtualenv.."
source "$VENV_DIR/bin/activate"

echo "Upgrading pip.."
pip install --upgrade pip

echo "Installing python dependencies.."
pip install  python-openstackclient
pip install  requests
pip install  setuptools


echo ""
echo "Setup complete."
echo ""
echo "To use this environment in the future or CI/CD jobs, activate the virtualenv:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "To safely remove this virtualenv later, run:"
echo "    $0 --remove-venv"
echo ""

source "$VENV_DIR/bin/activate"
