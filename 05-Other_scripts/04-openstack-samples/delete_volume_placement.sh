#!/bin/bash

echo "Fetching list of images..."
openstack image list --long -f value -c ID -c Name -c Status | while read -r image_id image_name image_status; do
    if [[ "$image_status" == "active" ]]; then
        echo "Deleting image: $image_name ($image_id)"
        openstack image delete "$image_id"
    else
        echo "Skipping image: $image_name ($image_id) - status is $image_status"
    fi
done
