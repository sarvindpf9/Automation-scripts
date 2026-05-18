# 03-python_deployment_automation

End-to-end OpenStack instance provisioning script that creates a network, subnet, image, volume, and Nova server from a single CLI invocation, with matching teardown support.

---

## `create_instance_e2e.py`

Orchestrates full resource lifecycle on an OpenStack cloud using openstacksdk. On create, it provisions a Neutron network and subnet, uploads a local image to Glance, creates a Cinder volume, and boots a Nova instance. On delete, it tears down all named resources in reverse order.

**Dependencies (local):**

- `openstacksdk` — OpenStack Python SDK (`pip3 install openstacksdk`)
- `clouds.yaml` — credential config at `~/.config/openstack/clouds.yaml` or `/etc/openstack/clouds.yaml`
- `modules/helper.py` — local module bundled in this directory

**Dependencies (remote):**

- Keystone — authentication and service catalog resolution
- Neutron — network and subnet operations
- Glance — image upload (requires a cloud user with image-create rights)
- Cinder — volume creation
- Nova — server boot and status polling

**What it does:**

1. Resolves connections for the target cloud (and optionally a separate admin cloud for image upload)
2. Creates a Neutron network and a `/24` subnet (`192.168.100.0/24`)
3. Uploads a local `qcow2` image to Glance; waits for `active` status
4. Creates a Cinder volume (3 GB); waits for `available` status
5. Looks up the specified flavor and image by name, then boots a Nova server
6. Waits up to 300 s for the server to reach `active`; prints confirmation

With `--delete`: removes server (with a 20 s drain), volume, subnet, network, and image matched by `<name>` prefix.

### Usage

```bash
# Create — upload a local image via admin cloud, then boot
python3 create_instance_e2e.py \
  --cloud <CLOUD_NAME> \
  --admin-cloud <ADMIN_CLOUD_NAME> \
  --name <BASE_NAME> \
  --image-file <PATH_TO_QCOW2>

# Create — use an existing Glance image by name (no upload, no admin cloud needed)
python3 create_instance_e2e.py \
  --cloud <CLOUD_NAME> \
  --name <BASE_NAME> \
  --image-name <EXISTING_IMAGE_NAME>

# Delete all resources matching the base name
python3 create_instance_e2e.py \
  --cloud <CLOUD_NAME> \
  --name <BASE_NAME> \
  --delete
```

### Options

| Flag | Required | Description |
| ---- | -------- | ----------- |
| `--cloud CLOUD_NAME` | Yes | Cloud profile name from `clouds.yaml` |
| `--admin-cloud CLOUD_NAME` | Only with `--image-file` | Cloud profile for Glance image upload; must expose the admin endpoint |
| `--name BASE_NAME` | Yes | Base name prefix used for all created resources |
| `--image-file PATH` | One of these required (create) | Local `qcow2` path to upload to Glance; requires `--admin-cloud` |
| `--image-name NAME` | One of these required (create) | Existing Glance image name to use directly; skips upload |
| `--delete` | No | Tear down all resources matching `BASE_NAME` instead of creating |

### Examples

```bash
# Create — upload local image via admin cloud, boot with public cloud creds
python3 create_instance_e2e.py \
  --cloud mycloud \
  --admin-cloud mycloud_admin \
  --name testvm01 \
  --image-file ~/images/cirros-0.6.3-x86_64-disk.img

# Create — use an existing Glance image; no upload, no admin cloud required
python3 create_instance_e2e.py \
  --cloud mycloud \
  --name testvm01 \
  --image-name cirros-0.6.3-x86_64

# Delete all testvm01-* resources
python3 create_instance_e2e.py \
  --cloud mycloud \
  --name testvm01 \
  --delete
```

### `clouds.yaml` configuration

Populate `~/.config/openstack/clouds.yaml` with at least one cloud profile. The `--admin-cloud` profile is only required if your regular user lacks `image-create` rights.

> **Note:** The fields `auth_url`, `username`, `password`, and `project_name` contain sensitive credentials. Do not commit a populated `clouds.yaml` to version control.

```yaml
clouds:
  mycloud:
    auth:
      auth_url: https://<DU_FQDN>/keystone/v3
      username: "<USERNAME>"
      password: "<PASSWORD>"
      project_name: "<PROJECT_NAME>"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "<REGION_NAME>"
    identity_api_version: 3
    interface: "public"
    verify: false

  mycloud_admin:                  # optional — only needed with --admin-cloud
    auth:
      auth_url: https://<DU_FQDN>/keystone/v3
      username: "<ADMIN_USERNAME>"
      password: "<ADMIN_PASSWORD>"
      project_name: "<ADMIN_PROJECT>"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "<REGION_NAME>"
    identity_api_version: 3
    interface: "admin"
    verify: false
```

### Pre-check behaviour

| Check | Applies to |
| ----- | ---------- |
| Flavor lookup by name — raises exception if not found | create only |
| Image lookup by ID after upload — raises exception if not found | create only |
| Volume and image status polling with 300 s timeout | create only |
| 20 s drain sleep after server delete before volume removal | delete only |

### Subnet CIDR

The subnet is hardcoded to `192.168.100.0/24` in `modules/helper.py:create_subnet`. If this conflicts with an existing network in your project, edit that function before running.
