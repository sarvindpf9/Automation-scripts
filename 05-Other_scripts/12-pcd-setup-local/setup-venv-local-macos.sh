#!/bin/bash
set -euo pipefail

VENV_DIR=".venv-local"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ "${1:-}" = "--remove-venv" ]; then
  echo "Requested removal of virtual environment at $VENV_DIR"

  if [ -d "$VENV_DIR" ]; then
    if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" = "$(cd "$VENV_DIR"; pwd)" ]; then
      echo "The virtualenv is active in this shell."
      echo "Run 'deactivate' first, then re-run: $0 --remove-venv"
      exit 1
    fi

    echo "Removing virtualenv directory $VENV_DIR..."
    rm -rf "$VENV_DIR"
    echo "Virtual environment removed."
  else
    echo "Virtual environment directory $VENV_DIR does not exist. Nothing to remove."
  fi

  exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script is intended for macOS only."
  echo "For Linux, use ./setup-venv-local.sh"
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || ! "$PYTHON_BIN" -c 'import sys' >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3 not found. Installing Python with Homebrew..."
    brew install python
  else
    echo "Python 3 is required but was not found."
    echo "Install Python 3 from https://www.python.org/downloads/macos/ or install Homebrew and run:"
    echo "    brew install python"
    exit 1
  fi
fi

echo ""
echo "Using Python interpreter: $($PYTHON_BIN -c 'import sys; print(sys.executable)')"
echo "Python version: $($PYTHON_BIN --version)"

PYVER=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info >= (3,9))')
if [ "$PYVER" != "True" ]; then
  echo "Python 3.9 or newer is required. Found: $($PYTHON_BIN --version)"
  exit 1
fi

echo ""
echo "Setting up Python virtual environment at $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

echo "Activating virtualenv.."
source "$VENV_DIR/bin/activate"

echo "Installing python dependencies.."
python -m pip install --upgrade pip setuptools wheel
python -m pip install python-openstackclient requests

echo ""
echo "Setup complete."
echo ""
echo "To use this environment in the future or CI/CD jobs, activate the virtualenv:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "To safely remove this virtualenv later, run:"
echo "    $0 --remove-venv"
echo ""
