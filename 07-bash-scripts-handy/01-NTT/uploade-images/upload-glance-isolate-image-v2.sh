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

GLANCE_HOSTS=(
    "10.196.85.11:9494"
)

GLANCE_SCHEME=${GLANCE_SCHEME:-https}

CURL_OPTIONS=(
    --silent
    --show-error
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

_TMPFILES=()
_cleanup() {
    [[ ${#_TMPFILES[@]} -gt 0 ]] && rm -f "${_TMPFILES[@]}"
}
trap _cleanup EXIT

_tmpfile() {
    local f
    f=$(mktemp)
    _TMPFILES+=("$f")
    printf '%s' "$f"
}

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

    _hc_body=$(_tmpfile)
    _hc=$(
        curl "${CURL_OPTIONS[@]}" \
            --max-time 10 \
            -H "X-Auth-Token: $TOKEN" \
            --output "$_hc_body" \
            --write-out '%{http_code}' \
            "${candidate}/v2/images?limit=1"
    ) || _hc="000"

    if [[ "$_hc" == "200" ]]; then
        GLANCE_ENDPOINT=$candidate
        echo "Using Glance endpoint: $GLANCE_ENDPOINT"
        break
    fi

    echo "Glance API check returned HTTP $_hc for $candidate; trying next..." >&2
done

[[ -n "$GLANCE_ENDPOINT" ]] || {
    echo "ERROR: No usable Glance endpoint found" >&2
    exit 1
}

CREATE_PAYLOAD=$(
    python3 - "$IMAGE_NAME" "$DISK_FORMAT" "$IMAGE_VISIBILITY" <<'PY'
import json
import sys

print(json.dumps({
    "name":             sys.argv[1],
    "disk_format":      sys.argv[2],
    "container_format": "bare",
    "visibility":       sys.argv[3],
}))
PY
)

_create_body=$(_tmpfile)
_create_http=$(
    curl "${CURL_OPTIONS[@]}" \
        --max-time 30 \
        --request POST \
        -H "X-Auth-Token: $TOKEN" \
        -H "Content-Type: application/json" \
        --data "$CREATE_PAYLOAD" \
        --output "$_create_body" \
        --write-out '%{http_code}' \
        "${GLANCE_ENDPOINT}/v2/images"
) || _create_http="000"

if [[ "$_create_http" != "201" ]]; then
    echo "ERROR: Image create failed (HTTP $_create_http)" >&2
    cat "$_create_body" >&2
    exit 1
fi

IMAGE_ID=$(
    python3 -c '
import json, sys

r = json.load(sys.stdin)
iid = r.get("id")
if not iid:
    raise SystemExit("Glance create response did not contain an image ID")
print(iid)
' < "$_create_body"
) || {
    echo "ERROR: Failed to parse image ID from Glance create response" >&2
    cat "$_create_body" >&2
    exit 1
}

echo "Created image record: $IMAGE_ID"

if stat -c '%s' "$IMAGE_FILE" >/dev/null 2>&1; then
    IMAGE_SIZE=$(stat -c '%s' "$IMAGE_FILE")   # Linux
else
    IMAGE_SIZE=$(stat -f '%z' "$IMAGE_FILE")   # BSD/macOS
fi


UPLOAD_RESPONSE_FILE=$(_tmpfile)
UPLOAD_TRACE_FILE=$(_tmpfile)

HTTP_CODE=$(
    curl "${CURL_OPTIONS[@]}" \
        --verbose \
        --request PUT \
        -H "X-Auth-Token: $TOKEN" \
        -H "Content-Type: application/octet-stream" \
        -H "X-OpenStack-Image-Size: $IMAGE_SIZE" \
        --data-binary "@$IMAGE_FILE" \
        --output "$UPLOAD_RESPONSE_FILE" \
        --write-out '%{http_code}' \
        "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}/file" \
        2>"$UPLOAD_TRACE_FILE"
) || HTTP_CODE="000"

if [[ "$HTTP_CODE" != "204" ]]; then
    echo "ERROR: Upload failed (HTTP $HTTP_CODE); attempting to remove image $IMAGE_ID" >&2
    cat "$UPLOAD_RESPONSE_FILE" >&2
    echo "--- curl verbose trace ---" >&2
    cat "$UPLOAD_TRACE_FILE" >&2

    curl "${CURL_OPTIONS[@]}" \
        --max-time 30 \
        --request DELETE \
        -H "X-Auth-Token: $TOKEN" \
        --output /dev/null \
        --write-out '' \
        "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}" || true

    exit 1
fi

_status_body=$(_tmpfile)
_status_http=$(
    curl "${CURL_OPTIONS[@]}" \
        --max-time 30 \
        -H "X-Auth-Token: $TOKEN" \
        --output "$_status_body" \
        --write-out '%{http_code}' \
        "${GLANCE_ENDPOINT}/v2/images/${IMAGE_ID}"
) || _status_http="000"

if [[ "$_status_http" != "200" ]]; then
    echo "ERROR: Status check failed (HTTP $_status_http)" >&2
    cat "$_status_body" >&2
    exit 1
fi

IMAGE_STATUS=$(
    python3 -c '
import json, sys
print(json.load(sys.stdin)["status"])
' < "$_status_body"
) || {
    echo "ERROR: Failed to parse image status from Glance response" >&2
    cat "$_status_body" >&2
    exit 1
}

if [[ "$IMAGE_STATUS" != active ]]; then
    echo "ERROR: Upload returned HTTP 204, but image status is '$IMAGE_STATUS' (expected 'active')" >&2
    exit 1
fi

echo "Upload complete. Image ID: $IMAGE_ID; status: $IMAGE_STATUS"
