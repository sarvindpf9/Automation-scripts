#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="/opt/scripts/hostcheck-tool-install"
VENV_DIR="${SCRIPTS_DIR}/venv"
REQ_FILE="${1:-${SCRIPTS_DIR}/requirements.txt}"
PYPI_INDEX="https://pypi.org/simple/"

if [ ! -d "${SCRIPTS_DIR}" ]; then
  echo "Creating ${SCRIPTS_DIR}"
  mkdir -p "${SCRIPTS_DIR}"
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating ${VENV_DIR}"
  mkdir -p "${VENV_DIR}"
fi


echo "copying script files to ${SCRIPTS_DIR} directory"
cp -r ./hostcheck_info.py ${SCRIPTS_DIR}
cp -r ./requirements.txt ${SCRIPTS_DIR}
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

echo "the hostcheck_info.py is placed in the ${SCRIPTS_DIR} directory"
echo "Run source ${VENV_DIR}/bin/activate before executing the script"
echo "Run ./hostcheck_info within the ${SCRIPTS_DIR} to fetch the current system assessment information"