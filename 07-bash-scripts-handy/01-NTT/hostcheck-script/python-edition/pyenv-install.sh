#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="/opt/scripts/hostcheck-tool-install"
VENV_DIR="${SCRIPTS_DIR}/venv"
REQ_FILE="${1:-${SCRIPTS_DIR}/requirements.txt}"
PYPI_INDEX="https://pypi.org/simple/"

if [ -r /etc/os-release ]; then
  # Install the matching venv package before invoking Python 3.12 on Ubuntu 24.04.
  . /etc/os-release
  if [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ]; then
    echo "Installing the Python virtual environment package for Ubuntu 24.04 LTS"
    apt-get install python3.12-venv -yy
  fi
fi

if [ ! -d "${SCRIPTS_DIR}" ]; then
  echo "Creating ${SCRIPTS_DIR}"
  mkdir -p "${SCRIPTS_DIR}"
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating ${VENV_DIR}"
  mkdir -p "${VENV_DIR}"
fi


echo "copying script files to ${SCRIPTS_DIR} directory"
cp -r ./hostinfo_check.py ${SCRIPTS_DIR}/hostinfo_check
if [ "$(readlink -f ./requirements.txt)" != "$(readlink -f "${SCRIPTS_DIR}/requirements.txt")" ]; then
  cp -r ./requirements.txt "${SCRIPTS_DIR}/requirements.txt"
fi
echo " "

echo "Setting up python environment"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --index-url "${PYPI_INDEX}" --upgrade pip
if [ ! -f "${REQ_FILE}" ]; then
  echo "Requirements file not found: ${REQ_FILE}" >&2
  exit 1
fi
"${VENV_DIR}/bin/python" -m pip install --index-url "${PYPI_INDEX}" -r "${REQ_FILE}"
echo " "

echo "the hostinfo_check.py is placed in the ${SCRIPTS_DIR} directory"
echo "Run source ${VENV_DIR}/bin/activate before executing the script"
echo "Run ./hostinfo_check within the ${SCRIPTS_DIR} to fetch the current system assessment information"
