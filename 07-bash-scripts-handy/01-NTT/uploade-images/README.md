# upload-images

Uploads a local image file directly to an available OpenStack Glance API endpoint. This script is specifically designed to work with [option 1 of the glance isolation per host cluster procedure](https://platform9.atlassian.net/wiki/spaces/eng/pages/6146261031/Manual+Configuration+for+Image+Service+in+AZ-Specific+PCD+Deployments). Hence it is required to ensure the glance is configured properly before executing this script

> **Sensitive-data notice:** The script contains environment-specific private Glance endpoint IP addresses. They are intentionally not reproduced in this README. Review the embedded endpoint list before running the script outside its intended environment.

---

## `upload-glance-isolate-image.sh`

The script selects the first usable configured Glance endpoint, creates a public or private image record, uploads the local image data, and verifies that the resulting image is active.

**Dependencies (local):**

- Bash
- `openstack` CLI with working OpenStack authentication environment variables or a sourced credentials file
- `curl` with `--fail-with-body` support
- Python 3 for JSON creation and response parsing
- GNU or BSD/macOS `stat` for determining the image size
- Network access to at least one Glance endpoint embedded in the script
- Permission to create images with the requested visibility in the target OpenStack project

**What it does:**

1. Validates the argument count, image visibility, and confirms that the image file is readable.
2. Obtains a Keystone token through the `openstack` CLI.
3. Tests each configured Glance endpoint and selects the first usable endpoint.
4. Creates a Glance image record with the requested visibility and `container_format` set to `bare`.
5. Determines the local file size and uploads the file using `curl --data-binary`.
6. Deletes the newly created image record if the upload request fails.
7. Retrieves the image record and succeeds only when its status is `active`.

### Usage

- Modify the `GLANCE_HOSTS` variable in the script with the admin endpoint list for a given host cluster.
- Download the required images to be uploaded withing the cluster

```bash
# Upload an image using the default qcow2 disk format
 CURL_INSECURE=1 ./upload-glance-isolate-image.sh <IMAGE_FILE> <IMAGE_NAME>

# Upload an image using an explicit Glance disk format
 CURL_INSECURE=1 ./upload-glance-isolate-image.sh <IMAGE_FILE> <IMAGE_NAME> <DISK_FORMAT>

# Upload a private image using an explicit Glance disk format
 CURL_INSECURE=1 ./upload-glance-isolate-image.sh <IMAGE_FILE> <IMAGE_NAME> <DISK_FORMAT> private
```

> **Image names:** Ensure the images carry prefixes or other ways to ensure user/operator can identify the image and its belonging host cluster so the VMs can be launched successfully.

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `IMAGE_FILE` | Yes | Path to a readable local image file. |
| `IMAGE_NAME` | Yes | Name assigned to the Glance image. Quote names containing spaces. |
| `DISK_FORMAT` | No | Disk format passed to Glance. Defaults to `qcow2`; the script does not validate the supplied value or compare it with the file extension. |
| `IMAGE_VISIBILITY` | No | Glance image visibility. Defaults to `public`; accepted values are `public` and `private`. |

### TLS environment variables

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `GLANCE_SCHEME` | No | URL scheme used for Glance endpoints. Defaults to `https`. |
| `GLANCE_CA_CERT` | No | Path to a readable CA certificate used by all direct Glance API requests. |
| `CURL_INSECURE` | No | Set to `1` to disable TLS certificate verification for direct Glance API requests when `GLANCE_CA_CERT` is unset. |

`GLANCE_CA_CERT` takes precedence over `CURL_INSECURE`. Token retrieval always uses `openstack --insecure`, independently of these variables.

### Examples

```bash
# Source the OpenStack credentials required by the openstack CLI
source <OPENSTACK_RC_FILE>

# Upload a qcow2 image using the default disk format
CURL_INSECURE=1 ./upload-glance-isolate-image.sh \
  <IMAGE_FILE>.qcow2 \
  <IMAGE_NAME>


# Upload a raw image when TLS certificate verification must be disabled
CURL_INSECURE=1 \
  ./upload-glance-isolate-image.sh \
  <IMAGE_FILE>.raw \
  <IMAGE_NAME> \
  raw

# Upload a private qcow2 image
CURL_INSECURE=1 ./upload-glance-isolate-image.sh \
  <IMAGE_FILE>.qcow2 \
  <IMAGE_NAME> \
  qcow2 \
  private
```

### Pre-check behaviour

| Check | Applies to |
| ---- | ---------- |
| Argument count is between two and four | upload |
| Image file exists, is a regular file, and is readable | upload |
| Image visibility is `public` or `private` | upload |
| `GLANCE_CA_CERT` is readable when supplied | direct Glance requests |
| Keystone returns a non-empty token | upload |
| At least one configured Glance endpoint responds successfully | upload |

### Operational constraints

- The image visibility defaults to `public`; pass `private` as the fourth argument when project-only access is required.
- The script does not validate `DISK_FORMAT`; Glance rejects unsupported values.
- The upload has no retry, resumable-transfer, checksum-verification, or token-refresh logic. A network interruption requires running the script again.
- Endpoint failover occurs only during the initial API check. The script does not switch endpoints if image creation, upload, or final verification fails.
- The upload request has a five-second connection timeout but no overall transfer timeout.
- A failed upload request triggers deletion of the newly created image record. A successful upload followed by a non-`active` status does not trigger deletion.

### Verification

Use the image ID printed by the script:

```bash
openstack image show <IMAGE_ID> \
  --format value \
  --column status
```

The expected status is:

```
active
```
