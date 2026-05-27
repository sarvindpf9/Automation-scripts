#!/usr/bin/env bash
# glance-image-inventory.sh
# List Glance images belonging to the local cluster via NFS mount correlation.
# Requires: openstack CLI, OS_* env or clouds.yaml, jq, stat
# Run on: any host with Glance role and NFS mount access.

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_NAME=$(basename "$0")
NFS_MOUNT="${GLANCE_NFS_MOUNT:-}"        # override via env or -m flag
OS_REGION="${OS_REGION_NAME:-}"          # override via env or -r flag
CLOUD="${OS_CLOUD:-}"                    # clouds.yaml profile, optional
OUTPUT_FORMAT="table"                    # table | csv | xlsx
OUTPUT_FILE=""                           # required for xlsx; optional for csv
SHOW_MISSING=false                       # include images with no NFS file found

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME -m <nfs_mount_path> -r <region> [-c <cloud_profile>] [-f table|csv|xlsx] [-o <output_file>] [--show-missing]

  -m  NFS mount path where Glance stores image files  (e.g. /var/lib/glance/images)
  -r  OpenStack region name                           (e.g. RegionOne)
  -c  clouds.yaml profile name                        (optional, overrides OS_CLOUD)
  -f  Output format: table (default), csv, or xlsx
  -o  Write output to file — required for xlsx, optional for csv
  --show-missing  Include images whose file is absent from the NFS mount

Environment fallbacks: GLANCE_NFS_MOUNT, OS_REGION_NAME, OS_CLOUD
EOF
  exit 1
}

# ── Arg parse ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m) NFS_MOUNT="$2"; shift 2 ;;
    -r) OS_REGION="$2"; shift 2 ;;
    -c) CLOUD="$2"; shift 2 ;;
    -f) OUTPUT_FORMAT="$2"; shift 2 ;;
    -o) OUTPUT_FILE="$2"; shift 2 ;;
    --show-missing) SHOW_MISSING=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$NFS_MOUNT" ]] && { echo "ERROR: NFS mount path required (-m or GLANCE_NFS_MOUNT)"; usage; }
[[ -z "$OS_REGION" ]] && { echo "ERROR: Region required (-r or OS_REGION_NAME)"; usage; }
[[ -d "$NFS_MOUNT" ]] || { echo "ERROR: NFS mount not accessible: $NFS_MOUNT"; exit 1; }

if [[ "$OUTPUT_FORMAT" == "xlsx" ]]; then
  [[ -z "$OUTPUT_FILE" ]] && { echo "ERROR: -o <output_file.xlsx> is required when using -f xlsx"; exit 1; }
  python3 -c "import openpyxl" 2>/dev/null \
    || { echo "ERROR: python3 + openpyxl required for xlsx output — run: pip install openpyxl"; exit 1; }
fi

# ── OpenStack CLI base args ───────────────────────────────────────────────────
OS_ARGS=(--os-region-name "$OS_REGION")
[[ -n "$CLOUD" ]] && OS_ARGS+=(--os-cloud "$CLOUD")

# ── Verify Glance endpoint reachable for this region ─────────────────────────
echo "==> Verifying Glance endpoint for region: $OS_REGION"
GLANCE_ENDPOINT=$(openstack "${OS_ARGS[@]}" endpoint list \
  --service image --interface public -f json 2>/dev/null \
  | jq -r --arg region "$OS_REGION" \
    '.[] | select(.["Region"] == $region) | .URL' | head -1)

if [[ -z "$GLANCE_ENDPOINT" ]]; then
  echo "ERROR: No public Glance endpoint found for region '$OS_REGION'"
  exit 1
fi
echo "    Endpoint : $GLANCE_ENDPOINT"

# ── Fetch all images from this region's Glance ───────────────────────────────
echo "==> Fetching image list from Glance ..."
IMAGE_JSON=$(openstack "${OS_ARGS[@]}" image list \
  --all-projects --long -f json 2>/dev/null)

IMAGE_COUNT=$(echo "$IMAGE_JSON" | jq 'length')
echo "    Found    : $IMAGE_COUNT image(s)"

# ── Prepare temp CSV for xlsx mode ───────────────────────────────────────────
TMPCSV=""
if [[ "$OUTPUT_FORMAT" == "xlsx" ]]; then
  TMPCSV=$(mktemp /tmp/glance-XXXXXX.csv)
  trap 'rm -f "$TMPCSV"' EXIT
  printf 'ID,Name,Status,Size(MiB),DiskFormat,ContainerFormat,Visibility,Owner,OnNFS,NFSPath\n' \
    > "$TMPCSV"
fi

# ── Correlate each image ID against NFS mount ────────────────────────────────
echo "==> Correlating image IDs with NFS mount: $NFS_MOUNT"
echo ""

# ── Output header (table / csv modes) ────────────────────────────────────────
if [[ "$OUTPUT_FORMAT" == "table" ]]; then
  printf "%-38s  %-36s  %-10s  %10s  %-10s  %-10s  %-10s  %-32s  %s\n" \
    "ID" "Name" "Status" "Size(MiB)" "DiskFmt" "CntrFmt" "Visibility" "Owner" "NFS File"
  printf '%s\n' "$(printf '─%.0s' {1..160})"
elif [[ "$OUTPUT_FORMAT" == "csv" ]]; then
  _csv_out() { printf '%s' "$*"; }
  if [[ -n "$OUTPUT_FILE" ]]; then
    printf 'ID,Name,Status,Size(MiB),DiskFormat,ContainerFormat,Visibility,Owner,OnNFS,NFSPath\n' \
      > "$OUTPUT_FILE"
  else
    printf 'ID,Name,Status,Size(MiB),DiskFormat,ContainerFormat,Visibility,Owner,OnNFS,NFSPath\n'
  fi
fi

# ── Per-image processing ──────────────────────────────────────────────────────
MATCHED=0
MISSING=0

while IFS= read -r image; do
  id=$(echo "$image"          | jq -r '.ID // .id')
  name=$(echo "$image"        | jq -r '.Name // .name // "<unnamed>"')
  status=$(echo "$image"      | jq -r '.Status // .status')
  size_bytes=$(echo "$image"  | jq -r '.Size // .size // 0')
  disk_fmt=$(echo "$image"    | jq -r '."Disk Format" // .disk_format // "?"')
  ctr_fmt=$(echo "$image"     | jq -r '."Container Format" // .container_format // "?"')
  visibility=$(echo "$image"  | jq -r '.Visibility // .visibility // "?"')
  owner=$(echo "$image"       | jq -r '."Project" // .owner // "?"')

  if [[ "$size_bytes" =~ ^[0-9]+$ ]] && (( size_bytes > 0 )); then
    size_mib=$(( size_bytes / 1048576 ))
  else
    size_mib="N/A"
  fi

  # Glance flat layout: <mount>/<uuid>
  nfs_path="${NFS_MOUNT}/${id}"
  if [[ -f "$nfs_path" ]]; then
    on_nfs="YES"
    file_info="$nfs_path"
    (( MATCHED++ )) || true
  else
    on_nfs="NO"
    file_info="<not found>"
    (( MISSING++ )) || true
    [[ "$SHOW_MISSING" == false ]] && continue
  fi

  case "$OUTPUT_FORMAT" in
    table)
      printf "%-38s  %-36s  %-10s  %10s  %-10s  %-10s  %-10s  %-32s  %s\n" \
        "$id" "${name:0:36}" "$status" "$size_mib" "$disk_fmt" "$ctr_fmt" \
        "$visibility" "${owner:0:32}" "$file_info"
      ;;
    csv)
      _row=$(printf '"%s","%s","%s","%s","%s","%s","%s","%s","%s","%s"\n' \
        "$id" "$name" "$status" "$size_mib" "$disk_fmt" "$ctr_fmt" \
        "$visibility" "$owner" "$on_nfs" "$file_info")
      if [[ -n "$OUTPUT_FILE" ]]; then
        printf '%s\n' "$_row" >> "$OUTPUT_FILE"
      else
        printf '%s\n' "$_row"
      fi
      ;;
    xlsx)
      printf '"%s","%s","%s","%s","%s","%s","%s","%s","%s","%s"\n' \
        "$id" "$name" "$status" "$size_mib" "$disk_fmt" "$ctr_fmt" \
        "$visibility" "$owner" "$on_nfs" "$file_info" \
        >> "$TMPCSV"
      ;;
  esac

done < <(echo "$IMAGE_JSON" | jq -c '.[]')

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
printf '%s\n' "$(printf '─%.0s' {1..160})"
printf "Region   : %s\n"   "$OS_REGION"
printf "Endpoint : %s\n"   "$GLANCE_ENDPOINT"
printf "NFS Mount: %s\n"   "$NFS_MOUNT"
printf "Total    : %d\n"   "$IMAGE_COUNT"
printf "On NFS   : %d\n"   "$MATCHED"
printf "Missing  : %d  (use --show-missing to include in output)\n" "$MISSING"

if [[ "$OUTPUT_FORMAT" == "csv" && -n "$OUTPUT_FILE" ]]; then
  echo "==> CSV written to: $OUTPUT_FILE"
fi

# ── XLSX generation ───────────────────────────────────────────────────────────
if [[ "$OUTPUT_FORMAT" == "xlsx" ]]; then
  echo "==> Generating Excel workbook ..."
  python3 - "$TMPCSV" "$OUTPUT_FILE" "$OS_REGION" "$GLANCE_ENDPOINT" \
    "$NFS_MOUNT" "$IMAGE_COUNT" "$MATCHED" "$MISSING" <<'PYEOF'
import sys
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime, timezone

csv_file, out_file, region, endpoint, nfs_mount, total, matched, missing = sys.argv[1:]

wb = openpyxl.Workbook()

# ── Images sheet ──────────────────────────────────────────────────────────────
ws = wb.active
ws.title = "Glance Images"

HDR_FONT  = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
HDR_FILL  = PatternFill(fill_type="solid", fgColor="1F4E79")
HDR_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
YES_FILL  = PatternFill(fill_type="solid", fgColor="C6EFCE")   # green
NO_FILL   = PatternFill(fill_type="solid", fgColor="FFC7CE")   # red
THIN      = Side(style="thin", color="BFBFBF")
BORDER    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
DATA_FONT = Font(name="Calibri", size=10)

col_widths = []

with open(csv_file, newline="") as f:
    reader = csv.reader(f)
    for row_idx, row in enumerate(reader, start=1):
        ws.append(row)
        # Track max width per column for auto-fit
        for col_idx, val in enumerate(row, start=1):
            needed = len(str(val)) + 2
            if len(col_widths) < col_idx:
                col_widths.append(needed)
            else:
                col_widths[col_idx - 1] = max(col_widths[col_idx - 1], needed)

        if row_idx == 1:
            for cell in ws[row_idx]:
                cell.font  = HDR_FONT
                cell.fill  = HDR_FILL
                cell.alignment = HDR_ALIGN
                cell.border = BORDER
        else:
            # Column 9 = OnNFS
            on_nfs_val = ws.cell(row=row_idx, column=9).value
            row_fill = YES_FILL if on_nfs_val == "YES" else NO_FILL
            for col_idx in range(1, len(row) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.fill   = row_fill
                cell.font   = DATA_FONT
                cell.border = BORDER
                cell.alignment = Alignment(vertical="center")

# Auto-fit column widths (cap at 60)
for col_idx, width in enumerate(col_widths, start=1):
    ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 60)

ws.row_dimensions[1].height = 30
ws.freeze_panes = "A2"
ws.auto_filter.ref = ws.dimensions

# ── Summary sheet ─────────────────────────────────────────────────────────────
ss = wb.create_sheet("Summary")
ss.title = "Summary"

SUM_HDR_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=12)
SUM_HDR_FILL = PatternFill(fill_type="solid", fgColor="1F4E79")
SUM_KEY_FONT = Font(bold=True, name="Calibri", size=11)
SUM_VAL_FONT = Font(name="Calibri", size=11)

summary_rows = [
    ("Field", "Value"),
    ("Report Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ("Region", region),
    ("Glance Endpoint", endpoint),
    ("NFS Mount", nfs_mount),
    ("Total Images", int(total)),
    ("On NFS (matched)", int(matched)),
    ("Missing from NFS", int(missing)),
]

for row_idx, (key, val) in enumerate(summary_rows, start=1):
    ss.cell(row=row_idx, column=1, value=key)
    ss.cell(row=row_idx, column=2, value=val)
    if row_idx == 1:
        for col in (1, 2):
            c = ss.cell(row=row_idx, column=col)
            c.font = SUM_HDR_FONT
            c.fill = SUM_HDR_FILL
            c.alignment = Alignment(horizontal="center")
    else:
        ss.cell(row=row_idx, column=1).font = SUM_KEY_FONT
        ss.cell(row=row_idx, column=2).font = SUM_VAL_FONT

ss.column_dimensions["A"].width = 28
ss.column_dimensions["B"].width = 60

wb.save(out_file)
print(f"    XLSX     : {out_file}")
PYEOF
fi
