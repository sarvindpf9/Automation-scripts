#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <PROJECT-NAME> <PROJECT-ID> <region-code>"
  exit 1
fi

PROJECT_NAME="$1"
PROJECT_ID="$2"
REGION_CODE="$3"
OUTPUT_FILE="${PROJECT_NAME}_${REGION_CODE}.txt"
LOG_FILE="${PROJECT_NAME}_${REGION_CODE}.log"

# ---------------- Fetch ACTIVE servers ----------------
openstack server list --project "$PROJECT_ID" \
  -f value -c ID -c Status |
  awk '$2 == "ACTIVE" {print $1}' > "$OUTPUT_FILE"

if [[ ! -s "$OUTPUT_FILE" ]]; then
  echo "No ACTIVE servers found for project $PROJECT_ID"
  exit 0
fi

echo "Finding and removing any default security group associated to the instance"

DEFAULT_SG_ID=$(openstack security group list --project "$PROJECT_ID" \
  -f value -c ID -c Name |
  awk '$2 == "default" {print $1}')

if [[ -z "$DEFAULT_SG_ID" ]]; then
  echo "WARNING: Default security group not found for project $PROJECT_ID"
else
  echo "Default security group ID: $DEFAULT_SG_ID"
fi

while read -r SERVER_ID; do
  ./portgrp_v2.sh "$SERVER_ID" "allow-all" "$PROJECT_ID"
done < "$OUTPUT_FILE" 2>&1 | tee "$LOG_FILE"

while read -r SERVER_ID; do
  if [[ -n "$DEFAULT_SG_ID" ]]; then
    REMOVE_OUTPUT=$(openstack server remove security group \
      "$SERVER_ID" "$DEFAULT_SG_ID" 2>&1) || true

    if echo "$REMOVE_OUTPUT" | grep -qi "NotFound"; then
      echo "INFO: No default security group associated with server $SERVER_ID"
    else
      echo "Default security group removed from server $SERVER_ID"
    fi
  fi
done < "$OUTPUT_FILE" 2>&1 | tee -a "$LOG_FILE"
