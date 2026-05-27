# 03-sample-windows-packer

Packer QEMU/KVM sample that builds a Windows qcow2 image, optionally attaches a software TPM through `swtpm`, injects curtin hooks, and keeps swtpm lifecycle handling in a standalone script.

---

## `windows.pkr.hcl`

Drives an unattended Windows installation with the QEMU builder. The template uses `http/Autounattend.xml`, `http/logon.ps1`, `http/rh.cer`, `drivers.iso`, and the host-side scripts under `scripts/`.

**Dependencies (build host):**

- `packer` >= 1.7.0 with the `github.com/hashicorp/qemu` plugin
- `qemu-system-x86_64`, `qemu-img`, `qemu-nbd` — QEMU/KVM build and image conversion tools
- `/dev/kvm` accessible — KVM acceleration is configured with `accelerator = "kvm"`
- `ovmf` firmware files under `/usr/share/OVMF/`
- `ntfs-3g`, `mount`, `umount`, `modprobe` — required by the post-processor path
- `swtpm` — required only when `enable_tpm=true`
- Root or sudo access for the build, because `scripts/setup-nbd` requires root and loads the `nbd` kernel module

**Dependencies (image content):**

- Windows installation ISO provided through `iso_path`
- `drivers.iso` in this directory, attached as a CD-ROM
- Network access from the Windows guest to download the Windows Driver Kit, Cloudbase-Init, and VirtIO installer files from the URLs in `http/logon.ps1`

**What it does:**

1. Boots the Windows ISO through QEMU/KVM with UEFI firmware from `/usr/share/OVMF/`. `OVMF_CODE` is attached read-only from the system path; `OVMF_VARS` is resolved from `ovmf_vars_path` when set, or the system path as a fallback. Copy `OVMF_VARS` to a local file before building so QEMU does not modify the shared system copy.
2. Attaches `http/Autounattend.xml`, `http/logon.ps1`, and `http/rh.cer` as floppy files.
3. Attaches `drivers.iso` as a CD-ROM for optional driver injection.
4. Adds TPM QEMU arguments only when `enable_tpm=true`.
5. Waits for the unattended Windows flow to shut down the VM.
6. Runs `scripts/finalize-windows-image` to mount the raw image, copy curtin hooks into partition 4, convert the raw image to qcow2, and remove the raw image.

### Ubuntu VM prerequisite setup

Run these commands on the Ubuntu build VM before the first build:

```bash
# Install host packages used by the QEMU builder and post-processor
sudo apt-get update
sudo apt-get install -y \
  curl \
  gnupg \
  lsb-release \
  qemu-kvm \
  qemu-utils \
  ovmf \
  ntfs-3g \
  swtpm

# Add the official HashiCorp apt repository for Packer
curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt-get update
sudo apt-get install -y packer

# Verify KVM access
test -e /dev/kvm

# Copy OVMF_VARS to a local writable file — QEMU modifies it during the build
cp /usr/share/OVMF/OVMF_VARS_4M.fd ./OVMF_VARS_4M.fd
```

If the Ubuntu build host is itself a VM, enable nested virtualization on the parent hypervisor before using this template. In a nested VM environment, also set `disable_hv_evmcs=true` in `variables.pkrvars.hcl` — the outer hypervisor typically does not expose the `hv-evmcs` CPU feature to guest VMs.

> **Sensitive data notice:** `http/Autounattend.xml` and `http/logon.ps1` contain a plaintext local Administrator password value. Replace it in your local working copy before production use and do not commit environment-specific credentials.

### Usage

```bash
# Initialise the QEMU plugin
packer init .

# Validate the template with the sample variables file
packer validate -var-file=variables.pkrvars.hcl windows.pkr.hcl

# Build without TPM (pass the local OVMF_VARS copy)
sudo packer build \
  -var-file=variables.pkrvars.hcl \
  -var 'ovmf_vars_path=./OVMF_VARS_4M.fd' \
  windows.pkr.hcl
```

```bash
# Build with TPM enabled
scripts/swtpm start
sudo packer build \
  -var-file=variables.pkrvars.hcl \
  -var enable_tpm=true \
  windows.pkr.hcl
scripts/swtpm stop
```

```bash
# Build with a custom output name
sudo packer build \
  -var-file=variables.pkrvars.hcl \
  -var 'qcow2_image_name=windows-server.qcow2' \
  windows.pkr.hcl
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `-var 'iso_path=<WINDOWS_ISO_PATH>'` | Yes | Path or URL to the Windows installation ISO. The template default is empty; `variables.pkrvars.hcl` carries the `<WINDOWS_ISO_PATH>` placeholder. |
| `-var 'headless=false'` | No | Run without opening a graphical console when set to `true`. Default in the template is `false`. |
| `-var 'disk_size=64G'` | No | Windows image disk size. Default is `64G`. |
| `-var 'disable_hv_evmcs=false'` | No | Uses `-cpu host,hv-evmcs` by default. Set to `true` on nested VMs or any host where the CPU does not expose `hv-evmcs`; falls back to `-cpu host`. |
| `-var 'ovmf_suffix=_4M'` | No | OVMF firmware filename suffix for `/usr/share/OVMF/OVMF_CODE<suffix>.ms.fd`. Default is `_4M`. |
| `-var 'ovmf_vars_path=<PATH>'` | No | Path to a local writable copy of the OVMF_VARS firmware file. When empty, falls back to `/usr/share/OVMF/OVMF_VARS<suffix>.fd`. Always set this to a local copy to prevent QEMU modifying the shared system file. |
| `-var 'enable_tpm=false'` | No | Adds TPM QEMU arguments when set to `true`. Start `scripts/swtpm` first. |
| `-var 'swtpm_socket_path=/tmp/swtpm/swtpm-sock'` | No | Socket path passed to QEMU for the TPM chardev. Must match `SWTPM_SOCKET_PATH` when that environment variable is used with `scripts/swtpm`. |
| `-var 'timeout=1h'` | No | Shutdown timeout for the Windows installer. Default is `1h`. |
| `-var 'output_directory=output-windows_builder'` | No | Directory for raw and qcow2 build artifacts. Default is `output-windows_builder`. |
| `-var 'raw_image_name=packer-windows_builder'` | No | Raw image filename created by the QEMU builder. Default is `packer-windows_builder`. |
| `-var 'qcow2_image_name=packer-windows-build.qcow2'` | No | Final qcow2 image filename. Default is `packer-windows-build.qcow2`. |

### Output

The default final image path is:

```text
output-windows_builder/packer-windows-build.qcow2
```

### Verification

```bash
# Confirm the final image exists and is qcow2
qemu-img info output-windows_builder/packer-windows-build.qcow2
```

---

## `scripts/swtpm`

Starts, stops, checks, restarts, or removes the software TPM state used when `enable_tpm=true`.

**Dependencies (local):**

- `bash` — script runtime
- `swtpm` — software TPM process started by this script
- Permission to create and remove files under `SWTPM_STATE_DIR`, defaulting to `/tmp/swtpm`

**Dependencies (hypervisor / remote host):**

- QEMU must use the same TPM socket path as the script. The default shared path is `/tmp/swtpm/swtpm-sock`.

**What it does:**

1. Resolves `SWTPM_STATE_DIR`, `SWTPM_SOCKET_PATH`, and `SWTPM_PID_FILE`, using defaults when unset.
2. Verifies `swtpm` exists before `start` or `restart`.
3. Starts `swtpm socket` in TPM 2.0 daemon mode with a Unix control socket.
4. Stores the process ID in the configured PID file.
5. Stops the process and removes the PID/socket files for `stop`.
6. Removes the full state directory for `clean`.

### Usage

```bash
# Start swtpm with default paths
scripts/swtpm start

# Check swtpm status
scripts/swtpm status

# Stop swtpm
scripts/swtpm stop

# Remove swtpm state
scripts/swtpm clean
```

```bash
# Start swtpm with custom state and socket paths
SWTPM_STATE_DIR=/tmp/windows-swtpm \
SWTPM_SOCKET_PATH=/tmp/windows-swtpm/swtpm-sock \
SWTPM_PID_FILE=/tmp/windows-swtpm/swtpm.pid \
scripts/swtpm start
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `start` | Yes | Starts `swtpm socket` if it is not already running. |
| `stop` | Yes | Stops the running `swtpm` process and removes the PID and socket files. |
| `restart` | Yes | Runs `stop`, then `start`. |
| `status` | Yes | Returns success only when the PID file exists and the process is running. |
| `clean` | Yes | Runs `stop`, then removes `SWTPM_STATE_DIR`. |
| `SWTPM_STATE_DIR=/tmp/swtpm` | No | Environment variable for TPM state directory. Default is `/tmp/swtpm`. |
| `SWTPM_SOCKET_PATH=/tmp/swtpm/swtpm-sock` | No | Environment variable for the Unix socket path. Default is `${SWTPM_STATE_DIR}/swtpm-sock`. |
| `SWTPM_PID_FILE=/tmp/swtpm/swtpm.pid` | No | Environment variable for the PID file. Default is `${SWTPM_STATE_DIR}/swtpm.pid`. |

### TPM socket behaviour

The Packer variable `swtpm_socket_path` must point at the same socket created by `scripts/swtpm`. With defaults, no override is needed because both use `/tmp/swtpm/swtpm-sock`.

#### Verification

```bash
# Verify swtpm is running before starting a TPM-enabled build
scripts/swtpm status
```

#### Example outputs

```
swtpm started on /tmp/swtpm/swtpm-sock
swtpm is running with pid <PID>
swtpm stopped
```

---

## `scripts/finalize-windows-image`

Post-processes the raw Windows image after Packer shuts down the VM. It mounts partition 4, copies curtin hooks into the image, converts the raw disk to qcow2, and removes the raw disk.

**Dependencies (local):**

- `bash` — script runtime
- `sync`, `mktemp`, `mountpoint`, `mount`, `umount`, `cp`, `rmdir`
- `qemu-nbd`, `qemu-img`
- `scripts/setup-nbd`
- Root or sudo access, inherited from `scripts/setup-nbd`

**Dependencies (hypervisor / remote host):**

- Linux `nbd` kernel module available on the build host
- Partition 4 in the raw Windows image must be the NTFS system partition expected by the script

**What it does:**

1. Reads the raw image path from argument 1, defaulting to `output-windows_builder/packer-windows_builder`.
2. Reads the qcow2 output path from argument 2, defaulting to `output-windows_builder/packer-windows-build.qcow2`.
3. Syncs the raw image to disk.
4. Sources `scripts/setup-nbd` with `IMG_FMT="raw"` to bind the image to a free `/dev/nbd*` device.
5. Mounts `${nbd}p4` as NTFS and copies `./curtin/*` into `curtin/` inside the image.
6. Disconnects the NBD device.
7. Converts the raw image to qcow2 and removes the raw image.

### Usage

```bash
# Finalize the default raw image path
sudo scripts/finalize-windows-image

# Finalize explicit raw and qcow2 paths
sudo scripts/finalize-windows-image \
  output-windows_builder/packer-windows_builder \
  output-windows_builder/packer-windows-build.qcow2
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `output-windows_builder/packer-windows_builder` | No | Positional argument 1. Raw image path; default is `output-windows_builder/packer-windows_builder`. |
| `output-windows_builder/packer-windows-build.qcow2` | No | Positional argument 2. Final qcow2 path; default is `output-windows_builder/packer-windows-build.qcow2`. |

### Cleanup behaviour

The script traps `EXIT` and attempts to unmount the temporary directory, disconnect the selected NBD device, and remove the temporary directory. This cleanup runs even when the image mount or conversion fails.

---

## `scripts/setup-nbd`

Binds a Packer QEMU raw image to the first free `/dev/nbd*` device so the image partitions can be mounted by follow-on scripts.

**Dependencies (local):**

- `bash` — script runtime
- `modprobe`, `qemu-nbd`, `cat`, `basename`, `sleep`
- Root access; the script exits when `${UID}` is not `0`

**Dependencies (hypervisor / remote host):**

- Linux `nbd` kernel module available
- `/sys/class/block/nbd*` entries available after `modprobe nbd`

**What it does:**

1. Requires root execution.
2. Uses argument 1 as the disk path, or defaults to `output-windows_builder/packer-windows_builder`.
3. Sets `IMG_FMT` to `raw` when the environment variable is unset.
4. Verifies the disk path exists.
5. Loads the `nbd` kernel module.
6. Finds the first `/sys/class/block/nbd[0-9]*` entry with size `0`.
7. Writes the selected `/dev/nbd*` path to `/tmp/nbd.lock`.
8. Disconnects any stale binding and connects the image with `qemu-nbd`.
9. Waits up to 60 seconds for `${nbd}p1` to appear.

### Usage

```bash
# Bind the default raw image path
sudo scripts/setup-nbd

# Bind an explicit raw image path
sudo scripts/setup-nbd output-windows_builder/packer-windows_builder

# Bind with an explicit image format
sudo IMG_FMT=raw scripts/setup-nbd output-windows_builder/packer-windows_builder
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `output-windows_builder/packer-windows_builder` | No | Positional argument 1. Disk path to bind; default is `output-windows_builder/packer-windows_builder`. |
| `IMG_FMT=raw` | No | Environment variable passed to `qemu-nbd -f`. Default is `raw`. |

### Failure behaviour

The script exits when it is not run as root, when the disk path does not exist, or when no free `/dev/nbd*` device is found. It does not currently fail when partition creation times out; consumers should verify the expected partition exists before mounting.
