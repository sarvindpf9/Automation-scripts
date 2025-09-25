#!/bin/bash

export SPOT_ORGANIZATION_NAME=ops-opex-pcd-dev
export SPOT_CLOUDSPACE_NAME=$1
export SPOT_REFRESH_TOKEN=SJhVRv6Jl4smXzkljW9qLbmrtuK20WzcXHvQnROtI977m

export PAYLOAD="{\"organization_name\":\"$SPOT_ORGANIZATION_NAME\",\"cloudspace_name\":\"$SPOT_CLOUDSPACE_NAME\",\"refresh_token\":\"$SPOT_REFRESH_TOKEN\"}"

curl -s https://spot.rackspace.com/apis/auth.ngpc.rxt.io/v1/generate-kubeconfig -X POST --data-binary "$PAYLOAD" | jq -r .data.kubeconfig

