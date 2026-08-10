#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    echo "Usage: $0 IMAGE_FILE IMAGE_NAME [DISK_FORMAT]" >&2
    exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage

IMAGE_FILE=$1
IMAGE_NAME=$2
DISK_FORMAT=${3:-qcow2}

[[ -f "$IMAGE_FILE" && -r "$IMAGE_FILE" ]] || {
    echo "ERROR: Image file is not readable: $IMAGE_FILE" >&2
    exit 1
}

GLANCE_HOSTS=(
    "10.231.228.12:9494"
    "10.231.228.23:9494"
    "10.231.228.9:9494"
    "10.231.228.41:9494"
)

# Must match the protocol actually exposed on port 9494.
GLANCE_SCHEME=${GLANCE_SCHEME:-https}
CURL_OPTIONS=(
    --silent
    --show-error
    --fail-with-body
    --connect-timeout 5
)

if [[ -n ${GLANCE_CA_CERT:-} ]]; then
    [[ -f "$GLANCE_CA_CERT" && -r "$GLANCE_CA_CERT" ]] || {
        echo "ERROR: CA certificate is not readable: $GLANCE_CA_CERT" >&2
        exit 1
    }

    CURL_OPTIONS+=(--cacert "$GLANCE_CA_CERT")
elif [[ ${CURL_INSECURE:-0} == 1 ]]; then
    echo "WARNING: Glance TLS certificate verification is disabled" >&2
    CURL_OPTIONS+=(--insecure)
fi

TOKEN=$(
    openstack --insecure token issue \
        --format value \
        --column id
)

[[ -n "$TOKEN" ]] || {
    echo "ERROR: Failed to obtain a Keystone token" >&2
    exit 1
}

GLANCE_ENDPOINT=""

for host in "${GLANCE_HOSTS[@]}"; do
    candidate="${GLANCE_SCHEME}://${host}"

    echo "Checking Glance endpoint: $candidate"

    # Do not add a separate -k here. CURL_OPTIONS must control TLS
    # consistently for the health check and all subsequent requests.
    if curl "${CURL_OPTIONS[@]}" \
        --max-time 10 \
        -H "X-Auth-Token: $TOKEN" \
        "${candidate}/v2/images?limit=1" >/dev/null; then

        GLANCE_ENDPOINT=$candidate
        echo "Using Glance endpoint: $GLANCE_ENDPOINT"
        break
    fi

    echo "Glance API check failed for $candidate; trying next..." >&2
done

[[ -n "$GLANCE_ENDPOINT" ]] || {
    echo "ERROR: No usable Glance endpoint found" >&2
    exit 1
}

# Generate correctly escaped JSON.
CREATE_PAYLOAD=$(
    python3 - "$IMAGE_NAME" "$DISK_FORMAT" <<'PY'
import json
import sys

print(json.dumps({
    "name": sys.argv[1],
    "disk_format": sys.argv[2],
    "container_format": "bare",
    "visibility": "public",
}))
PY
)

CREATE_RESPONSE=$(
    curl "${CURL_OPTIONS[@]}" \
        --max-time 30 \
        --request POST \
        -H "X-Auth-Token: $TOKEN" \
        -H "Content-Type: application/json" \
        --data "$CREATE_PAYLOAD" \
        "${GLANCE_ENDPOINT}/v2/images"
)

IMAGE_ID=$(
    python3 -c '
import json
import sys

response = json.load(sys.stdin)
image_id = response.get("id")

if not image_id:
    raise SystemExit(
        "Glance create response did not contain an image ID"
    )

print(image_id)
' <<<"$CREATE_RESPONSE"
)

echo "Created image record: $IMAGE_ID"

# Optionally validates the size received by Glance.
if stat -c '%s' "$IMAGE_FILE" >/dev/null 2>&1; then
    IMAGE_SIZE=$(stat -c '%s' "$IMAGE_FILE")       # Linux
else
    IMAGE_SIZE=$(stat -f '%z' "$IMAGE_FILE")       # BSD/macOS
fi

if ! curl "${CURL_OPTIONS[@]}" \
    --request PUT \
    -H "X-Auth-Token: $TOKEN" \
    -H "Content-Type: application/octet-stream" \
    -H "X-OpenStack-Image-Size: $IMAGE_SIZE" \
    --data-binary "@$IMAGE_FILE" \
    "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}/file" >/dev/null; then

    echo "ERROR: Upload failed; attempting to remove image $IMAGE_ID" >&2

    curl "${CURL_OPTIONS[@]}" \
        --request DELETE \
        -H "X-Auth-Token: $TOKEN" \
        "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}" >/dev/null || true

    exit 1
fi

IMAGE_RESPONSE=$(
    curl "${CURL_OPTIONS[@]}" \
        --max-time 30 \
        -H "X-Auth-Token: $TOKEN" \
        "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}"
)

IMAGE_STATUS=$(
    python3 -c '
import json
import sys

print(json.load(sys.stdin)["status"])
' <<<"$IMAGE_RESPONSE"
)

if [[ "$IMAGE_STATUS" != active ]]; then
    echo "ERROR: Upload returned successfully, but image status is '$IMAGE_STATUS'" >&2
    exit 1
fi

echo "Upload complete. Image ID: $IMAGE_ID; status: $IMAGE_STATUS"
