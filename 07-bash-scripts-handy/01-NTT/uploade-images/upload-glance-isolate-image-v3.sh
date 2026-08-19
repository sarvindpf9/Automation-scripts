#!/usr/bin/env bash
# This is an updated test script for issue specifically seen for Atturra
set -Eeuo pipefail

usage() {
    echo "Usage: $0 IMAGE_FILE IMAGE_NAME [DISK_FORMAT] [IMAGE_VISIBILITY]" >&2
    echo "       DISK_FORMAT defaults to 'qcow2'." >&2
    echo "       IMAGE_VISIBILITY defaults to 'public'; accepted values: public, private." >&2
    exit 2
}

[[ $# -ge 2 && $# -le 4 ]] || usage

IMAGE_FILE=$1
IMAGE_NAME=$2
DISK_FORMAT=${3:-qcow2}
IMAGE_VISIBILITY=${4:-public}

[[ -f "$IMAGE_FILE" && -r "$IMAGE_FILE" ]] || {
    echo "ERROR: Image file is not readable: $IMAGE_FILE" >&2
    exit 1
}

case "$IMAGE_VISIBILITY" in
    public|private) ;;
    *)
        echo "ERROR: Invalid image visibility '$IMAGE_VISIBILITY'. Must be 'public' or 'private'." >&2
        exit 1
        ;;
esac

command -v openstack >/dev/null 2>&1 || {
    echo "ERROR: The openstack command is not installed or is not in PATH" >&2
    exit 1
}

command -v curl >/dev/null 2>&1 || {
    echo "ERROR: The curl command is not installed or is not in PATH" >&2
    exit 1
}

GLANCE_HOSTS=(
    "10.196.85.11:9494"
)

GLANCE_SCHEME=${GLANCE_SCHEME:-https}
export OS_INSECURE=true

if TOKEN=$(openstack token issue --format value --column id); then
    :
else
    OPENSTACK_EXIT_CODE=$?
    echo "ERROR: Failed to obtain a Keystone token; openstack exited with code $OPENSTACK_EXIT_CODE" >&2
    exit "$OPENSTACK_EXIT_CODE"
fi

[[ -n "$TOKEN" ]] || {
    echo "ERROR: OpenStack token issue succeeded but returned no token" >&2
    exit 1
}

OS_IMAGE_ENDPOINT_OVERRIDE=""
for host in "${GLANCE_HOSTS[@]}"; do
    candidate="${GLANCE_SCHEME}://${host}"
    echo "Checking Glance endpoint: $candidate"

    HTTP_CODE=$(
        curl \
            --silent \
            --show-error \
            --insecure \
            --connect-timeout 5 \
            --max-time 10 \
            --header "X-Auth-Token: $TOKEN" \
            --output /dev/null \
            --write-out '%{http_code}' \
            "${candidate}/v2/images?limit=1"
    ) || HTTP_CODE="000"

    if [[ "$HTTP_CODE" == 200 ]]; then
        OS_IMAGE_ENDPOINT_OVERRIDE=$candidate
        break
    fi

    echo "Glance endpoint $candidate returned HTTP $HTTP_CODE; trying next endpoint" >&2
done

[[ -n "$OS_IMAGE_ENDPOINT_OVERRIDE" ]] || {
    echo "ERROR: No usable Glance endpoint found" >&2
    exit 1
}

export OS_IMAGE_ENDPOINT_OVERRIDE

VISIBILITY_OPTION="--${IMAGE_VISIBILITY}"

echo "Uploading image to: $OS_IMAGE_ENDPOINT_OVERRIDE"
if IMAGE_ID=$(
    openstack image create \
        --container-format bare \
        --disk-format "$DISK_FORMAT" \
        "$VISIBILITY_OPTION" \
        --file "$IMAGE_FILE" \
        --format value \
        --column id \
        "$IMAGE_NAME"
); then
    :
else
    OPENSTACK_EXIT_CODE=$?
    echo "ERROR: OpenStack image creation/upload failed with exit code $OPENSTACK_EXIT_CODE" >&2
    exit "$OPENSTACK_EXIT_CODE"
fi

[[ -n "$IMAGE_ID" ]] || {
    echo "ERROR: OpenStack image create succeeded but returned no image ID" >&2
    exit 1
}

if IMAGE_STATUS=$(
    openstack image show \
        --format value \
        --column status \
        "$IMAGE_ID"
); then
    :
else
    OPENSTACK_EXIT_CODE=$?
    echo "ERROR: Unable to verify image $IMAGE_ID; openstack exited with code $OPENSTACK_EXIT_CODE" >&2
    exit "$OPENSTACK_EXIT_CODE"
fi

if [[ "$IMAGE_STATUS" != active ]]; then
    echo "ERROR: Image $IMAGE_ID has status '$IMAGE_STATUS' (expected 'active')" >&2
    exit 1
fi

echo "Upload complete. Image ID: $IMAGE_ID; status: $IMAGE_STATUS"
