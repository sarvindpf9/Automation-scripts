# glance-image-backend-check.sh

**Read-only** inventory tool that lists Glance images for an OpenStack region and correlates each image UUID against a Glance NFS backend mount, showing which images have a backing file on disk.

No write, delete, or mutating operations are performed at any point.

---

## Prerequisites

| Dependency | Purpose |
|---|---|
| `openstack` CLI | Queries the Glance API |
| `jq` | Parses JSON responses |
| `bash` ≥ 4.0 | Script runtime |
| Glance NFS mount accessible | File-existence correlation |
| `OS_*` env vars **or** `clouds.yaml` | Authentication to OpenStack |
| `python3` + `openpyxl` | Required only for `-f xlsx` output |

Install the xlsx dependency if needed:

```bash
pip install openpyxl
```

The script must be run on a host that has the Glance NFS mount path accessible (read access is sufficient).

---

## Usage

```bash
./glance-image-backend-check.sh -m <nfs_mount_path> -r <region> [OPTIONS]
```

### Required flags

| Flag | Description | Example |
|---|---|---|
| `-m <path>` | Path to the Glance NFS image store | `/var/lib/glance/images` |
| `-r <region>` | OpenStack region name | `RegionOne` |

### Optional flags

| Flag | Description | Default |
|---|---|---|
| `-c <profile>` | `clouds.yaml` profile name | `$OS_CLOUD` env var |
| `-f table\|csv\|xlsx` | Output format | `table` |
| `-o <file>` | Write output to file — required for `xlsx`, optional for `csv` | stdout |
| `--show-missing` | Include images with no NFS file found | off (matched only) |
| `-h`, `--help` | Print usage and exit | — |

### Environment variable fallbacks

Set these instead of passing flags every run:

```bash
export GLANCE_NFS_MOUNT=/var/lib/glance/images
export OS_REGION_NAME=RegionOne
export OS_CLOUD=mycloud          # optional, maps to a clouds.yaml profile
```

---

## Examples

**Basic table output — matched images only:**
```bash
./glance-image-backend-check.sh \
  -m /var/lib/glance/images \
  -r RegionOne
```

**Include images missing from NFS:**
```bash
./glance-image-backend-check.sh \
  -m /var/lib/glance/images \
  -r RegionOne \
  --show-missing
```

**CSV output written directly to file:**
```bash
./glance-image-backend-check.sh \
  -m /var/lib/glance/images \
  -r RegionOne \
  -f csv \
  -o glance-audit-$(date +%F).csv \
  --show-missing
```

**Excel (xlsx) output — formatted workbook with two sheets:**
```bash
./glance-image-backend-check.sh \
  -m /var/lib/glance/images \
  -r RegionOne \
  -f xlsx \
  -o glance-audit-$(date +%F).xlsx \
  --show-missing
```

**Using a specific `clouds.yaml` profile:**
```bash
./glance-image-backend-check.sh \
  -m /var/lib/glance/images \
  -r RegionOne \
  -c prod-cloud
```

**Using environment variables only:**
```bash
export GLANCE_NFS_MOUNT=/var/lib/glance/images
export OS_REGION_NAME=RegionOne
export OS_CLOUD=prod-cloud
./glance-image-backend-check.sh
```

---

## Output columns

| Column | Description |
|---|---|
| ID | Glance image UUID |
| Name | Image name (truncated to 36 chars in table mode) |
| Status | Glance image status (`active`, `queued`, `saving`, etc.) |
| Size (MiB) | Image size converted from bytes; `N/A` if unknown |
| DiskFmt | Disk format (`qcow2`, `raw`, `vmdk`, etc.) |
| CntrFmt | Container format (`bare`, `ovf`, etc.) |
| Visibility | `public`, `private`, `shared`, `community` |
| Owner | Project ID that owns the image (truncated to 32 chars in table mode) |
| NFS File | Full path if found on NFS; `<not found>` if absent |

A summary line is printed after the table with counts for total, matched, and missing images.

---

## Glance storage layout assumption

The script assumes Glance's default **flat** storage layout where image files are stored as `<nfs_mount>/<image-uuid>` with no subdirectories. If your deployment uses a chunked or subdirectory layout, the `nfs_path` construction on line 112 will need adjustment.

---

## Security notes

- Requires read access to the NFS mount and valid OpenStack credentials scoped to the target region.
- `--all-projects` in the `image list` call requires admin-level credentials to return images across all projects. Without admin scope, only images visible to the authenticated project are returned.
- No data is written, modified, or deleted by this script.
