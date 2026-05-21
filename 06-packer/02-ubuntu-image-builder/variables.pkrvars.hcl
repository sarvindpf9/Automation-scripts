# ── ISO source ─────────────────────────────────────────────────────────────────
# Download from: https://releases.ubuntu.com/24.04/
iso_url      = "<ISO_URL>"
iso_checksum = "sha256:<ISO_CHECKSUM_SHA256>"

# ── Build VM resources ─────────────────────────────────────────────────────────
disk_size = "20G"
memory    = 2048
cpus      = 2
headless  = true

# ── SSH credentials ────────────────────────────────────────────────────────────
# ssh_username must match the username in http/user-data.
# ssh_password must match the hashed password in http/user-data.
#
# Do NOT commit real passwords here. Pass via environment variable instead:
#   export PKR_VAR_ssh_password='your-password'
ssh_username = "<SSH_USERNAME>"
ssh_password = "<SSH_PASSWORD>"  # redacted — use PKR_VAR_ssh_password env var

# ── Output ─────────────────────────────────────────────────────────────────────
output_filename = "ubuntu-24.04.qcow2"
