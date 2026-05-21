# 02-ubuntu-image-builder

Packer QEMU/KVM template that builds a compressed Ubuntu 24.04 LTS qcow2 golden image with `qemu-guest-agent` enabled, user-defined `/etc/fstab` entries pre-populated, and user-defined `/etc/hosts` entries pre-populated.

---

## `linux.pkr.hcl`

Drives an unattended Ubuntu 24.04 installation via subiquity autoinstall, then runs shell provisioners to install packages and apply configuration before sealing the image into a compressed qcow2.

**Dependencies (build host):**

- `packer` >= 1.9.0 with the `hashicorp/qemu` plugin (`packer init .`)
- `qemu-system-x86_64`, `qemu-img` — QEMU/KVM toolchain
- `/dev/kvm` accessible — KVM acceleration is required; set `accelerator = "none"` in `variables.pkrvars.hcl` only if KVM is unavailable (build will be very slow)
- Network reachable from the build VM to the Packer HTTP server (default: host IP on the QEMU virtual network)

**Dependencies (image content):**

- Ubuntu 24.04 LTS server ISO (`ubuntu-24.04*-live-server-amd64.iso`) — download from `https://releases.ubuntu.com/24.04/`
- `qemu-guest-agent` — installed from Ubuntu repos during provisioning

**What it does:**

1. Boots the Ubuntu ISO in QEMU/KVM using the GRUB command line to pass the subiquity autoinstall seed URL
2. Subiquity fetches `http/user-data` from Packer's built-in HTTP server and performs an unattended LVM install
3. Packer waits up to `ssh_timeout` (default `40m`) for SSH — autoinstall + first reboot typically takes 15–25 min
4. Uploads `config/fstab_entries.conf` and `config/hosts_entries.conf` to the build VM via the `file` provisioner
5. Runs `scripts/provision.sh`: installs and enables `qemu-guest-agent`, appends non-comment lines from both config files to `/etc/fstab` and `/etc/hosts` without calling `mount -a`
6. Runs `scripts/cleanup.sh`: removes SSH host keys, resets `machine-id`, clears cloud-init state, removes the Packer sudoers rule, zeros free space
7. Post-processor converts the intermediate image to a compressed qcow2 at `output-linux_builder/<output_filename>`

### Pre-build setup

**1. Populate `variables.pkrvars.hcl`**

Fill in `iso_url`, `iso_checksum`, `ssh_username`, and `ssh_password`. Do **not** commit a plaintext password — pass it via environment variable instead:

```bash
export PKR_VAR_ssh_password='your-plaintext-password'
```

**2. Hash the password for `http/user-data`**

The `password:` field in `http/user-data` requires a SHA-512 hash. Generate it with:

```bash
openssl passwd -6 'your-plaintext-password'
```

Replace `<HASHED_PASSWORD>` in `http/user-data` with the output. The hash must correspond to the same plaintext as `PKR_VAR_ssh_password` — a mismatch will cause SSH authentication to fail after install.

> **Sensitive data notice:** `http/user-data` contains a hashed password and a username placeholder. Replace `<SSH_USERNAME>` and `<HASHED_PASSWORD>` with real values only in your local working copy. Add `variables.pkrvars.hcl` and `http/user-data` to `.gitignore` if your repo is shared.

**3. Edit customisation files (optional)**

Add entries to `config/fstab_entries.conf` and `config/hosts_entries.conf` before building. Lines starting with `#` and blank lines are ignored. See each file for format examples.

### Usage

```bash
# Initialise Packer plugins (first run only)
packer init .

# Validate the template
packer validate -var-file=variables.pkrvars.hcl linux.pkr.hcl

# Build the image
packer build -var-file=variables.pkrvars.hcl linux.pkr.hcl
```

```bash
# Build with headless=false to watch via VNC (debugging)
packer build \
  -var-file=variables.pkrvars.hcl \
  -var headless=false \
  linux.pkr.hcl
```

```bash
# Override output filename at build time
packer build \
  -var-file=variables.pkrvars.hcl \
  -var 'output_filename=ubuntu-24.04-custom.qcow2' \
  linux.pkr.hcl
```

### Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `iso_url` | `<ISO_URL>` | Full URL or local path to the Ubuntu 24.04 LTS server ISO |
| `iso_checksum` | `sha256:<ISO_CHECKSUM_SHA256>` | ISO checksum in `algorithm:value` format |
| `disk_size` | `20G` | Root disk size for the build VM |
| `memory` | `2048` | RAM in MB for the build VM |
| `cpus` | `2` | vCPUs for the build VM |
| `headless` | `true` | Set `false` to open VNC during build |
| `ssh_username` | `<SSH_USERNAME>` | Must match the username in `http/user-data` |
| `ssh_password` | `<SSH_PASSWORD>` | Plaintext; use `PKR_VAR_ssh_password` env var — do not commit |
| `ssh_timeout` | `40m` | Time Packer waits for SSH after first boot |
| `output_filename` | `ubuntu-24.04.qcow2` | Filename of the final qcow2 in `output-linux_builder/` |

### fstab behaviour

`config/fstab_entries.conf` is uploaded to the build VM and its non-comment lines are appended to `/etc/fstab`. `mount -a` is **never called** during the build — entries are written into the image so the deployed instance can mount them at boot or on demand. The build host is never affected.

Use `noauto` in the options field for entries that should not mount automatically on the deployed instance's first boot.

### /etc/hosts behaviour

`config/hosts_entries.conf` is uploaded and its non-comment lines are appended after the standard Ubuntu entries in `/etc/hosts`. The existing entries (localhost, `packer-build`) are preserved. If the file contains only comments, no changes are made and a message is printed.

### Sysprep (cleanup.sh)

Before the image is sealed, `cleanup.sh` performs the following on the build VM — these steps are **not optional** for a distributable golden image:

- Removes `/etc/sudoers.d/packer` (the passwordless-sudo rule injected during install)
- Removes SSH host keys (`/etc/ssh/ssh_host_*`) — each deployed instance regenerates its own on first boot
- Truncates `/etc/machine-id` and relinks `/var/lib/dbus/machine-id` — prevents UUID collisions across clones
- Resets cloud-init state so it reruns on first deployment
- Zeroes free space to improve qcow2 compression ratio

### Output

The final image lands at:

```
output-linux_builder/<output_filename>
```

Default: `output-linux_builder/ubuntu-24.04.qcow2`

### .gitignore recommendations

```gitignore
variables.pkrvars.hcl
output-linux_builder/
```

### Verification

After build, inspect the image with:

```bash
# Check image format and virtual size
qemu-img info output-linux_builder/ubuntu-24.04.qcow2

# Mount and verify fstab/hosts (requires nbd module)
sudo modprobe nbd
sudo qemu-nbd --connect=/dev/nbd0 output-linux_builder/ubuntu-24.04.qcow2
sudo mount /dev/nbd0p<N> /mnt
cat /mnt/etc/fstab
cat /mnt/etc/hosts
sudo umount /mnt
sudo qemu-nbd --disconnect /dev/nbd0
```
