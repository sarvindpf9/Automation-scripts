#!/bin/bash

## This script check the volume attachement list to verify if a volume is orphaned and prints the list


echo "Checking for orphaned volumes..."

# Get list of in-use volumes
volume_ids=$(openstack volume list --status in-use -f value -c ID)

for vol_id in $volume_ids; do
  # Get full volume details
  volume_info=$(openstack volume show "$vol_id" -f json)

  volume_name=$(echo "$volume_info" | jq -r '.name')
  attachment_json=$(echo "$volume_info" | jq -r '.attachments[0]')

  if [[ "$attachment_json" == "null" || -z "$attachment_json" ]]; then
    echo "Volume '$volume_name' ($vol_id) is marked in-use but has no attachments. Potential inconsistency."
    continue
  fi

  # Extract server_id and attachment_id
  server_id=$(echo "$attachment_json" | jq -r '.server_id')
  attachment_id=$(echo "$attachment_json" | jq -r '.attachment_id')

  # Check if server exists
  if ! openstack server show "$server_id" &>/dev/null; then
    echo "Orphaned volume found:"
    echo "Volume Name      : $volume_name"
    echo "Volume ID        : $vol_id"
    echo "Attachment ID    : $attachment_id"
    echo "Server ID (MISSING): $server_id"
  fi
done

