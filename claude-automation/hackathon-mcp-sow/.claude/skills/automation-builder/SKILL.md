# SKILL: build_automation

## Trigger
Use this skill when generating automation scripts via the `build_automation` MCP tool,
or when a user asks to build, write, or generate automation for Platform9 PCD or OpenStack
operations.

---

## Purpose
Generate working automation scripts (Python or Bash) for Platform9 Private Cloud Director
(OpenStack Epoxy+) operations. Scripts reference live Platform9 API docs and OpenStack API
references to produce correct, production-ready code.

---

## API Reference URLs

The generator fetches relevant docs based on task keywords:

| Keyword match | URLs fetched |
|---|---|
| `compute`, `vm`, `instance`, `nova`, `server` | OpenStack Compute API v2.1 |
| `network`, `neutron`, `port`, `subnet`, `router`, `security` | OpenStack Network API v2.0 |
| `volume`, `storage`, `cinder`, `snapshot`, `backup` | OpenStack Block Storage API v3 |
| `identity`, `keystone`, `token`, `project`, `user`, `role` | OpenStack Identity API v3 |
| `image`, `glance` | OpenStack Image API v2 |
| `platform9`, `pcd`, `pf9`, `blueprint`, `maas`, `host` | Platform9 API docs |
| (no match) | Platform9 API docs + Compute API |

Primary references:
- `https://docs.platform9.com/api-docs` — Platform9 PCD-specific APIs
- `https://docs.openstack.org/api-ref/compute/` — Nova
- `https://docs.openstack.org/api-ref/network/v2/` — Neutron
- `https://docs.openstack.org/api-ref/block-storage/v3/` — Cinder
- `https://docs.openstack.org/api-ref/identity/v3/` — Keystone
- `https://docs.openstack.org/api-ref/image/v2/` — Glance

---

## Authentication Pattern

### Python (keystoneauth1 / openstack SDK)
```python
import os
import openstack

conn = openstack.connect(
    auth_url=os.environ["OS_AUTH_URL"],
    project_name=os.environ["OS_PROJECT_NAME"],
    username=os.environ["OS_USERNAME"],
    password=os.environ["OS_PASSWORD"],
    user_domain_name=os.environ.get("OS_DOMAIN_NAME", "Default"),
    project_domain_name=os.environ.get("OS_PROJECT_DOMAIN_NAME", "Default"),
)
```

For direct REST calls (when openstack SDK doesn't cover the Platform9-specific API):
```python
from keystoneauth1 import loading, session
from keystoneauth1.identity import v3

auth = v3.Password(
    auth_url=os.environ["OS_AUTH_URL"],
    username=os.environ["OS_USERNAME"],
    password=os.environ["OS_PASSWORD"],
    project_name=os.environ["OS_PROJECT_NAME"],
    user_domain_name=os.environ.get("OS_DOMAIN_NAME", "Default"),
)
sess = session.Session(auth=auth)
token = sess.get_token()
```

### Bash (curl + jq)
```bash
#!/usr/bin/env bash
set -euo pipefail

TOKEN=$(curl -s -X POST "${OS_AUTH_URL}/auth/tokens" \
  -H "Content-Type: application/json" \
  -d "{
    \"auth\": {
      \"identity\": {
        \"methods\": [\"password\"],
        \"password\": {
          \"user\": {
            \"name\": \"${OS_USERNAME}\",
            \"password\": \"${OS_PASSWORD}\",
            \"domain\": {\"name\": \"${OS_DOMAIN_NAME:-Default}\"}
          }
        }
      },
      \"scope\": {
        \"project\": {\"name\": \"${OS_PROJECT_NAME}\",
          \"domain\": {\"name\": \"${OS_DOMAIN_NAME:-Default}\"}}
      }
    }
  }" -D - 2>/dev/null | grep -i "x-subject-token" | awk '{print $2}' | tr -d '\r')
```

---

## Code Quality Rules

All generated scripts must follow these rules unconditionally:

1. **File header**: usage example as a comment block at the top — one-liner showing how to run/call it
2. **Credentials from environment**: never hardcode credentials; always read from `OS_*` env vars
3. **Error handling**: catch specific exceptions (not bare `except`); log meaningful messages
4. **Pagination**: always handle paginated API responses (`marker`/`limit` or `next` links)
5. **Idempotency**: where possible, check-before-create patterns (don't fail if resource exists)
6. **Inline comments**: comment the *why* for non-obvious calls; annotate API endpoint paths
7. **Output**: print meaningful results, not raw JSON blobs; use tabular or structured output
8. **Dry-run flag**: for destructive operations (delete, reset, migrate), include a `--dry-run` flag
9. **Python style**: PEP8, type hints on all functions, f-strings, `argparse` for CLI scripts
10. **Bash style**: `set -euo pipefail`, meaningful variable names, `jq` for JSON parsing

---

## Common Task Patterns

### List all VMs across all projects (Python)
Use `conn.compute.servers(all_projects=True)` with admin credentials.

### Create security group with rules
Use `conn.network.create_security_group()` then `conn.network.create_security_group_rule()`.
Check idempotency: `conn.network.find_security_group(name)` before creating.

### Live migrate a VM
`conn.compute.live_migrate_server(server_id, host=None, block_migration=False)`
Check server status is ACTIVE first. Poll for MIGRATING → ACTIVE transition.

### Snapshot all volumes
Iterate `conn.block_storage.volumes()`, call `conn.block_storage.create_snapshot(volume_id=v.id, name=f"snap-{v.name}-{date}")`.
Handle `AVAILABLE` status check before snapshotting.

### Onboard host via Platform9 API (PCD-specific)
Use Platform9-specific `/resmgr/v1/hosts` endpoint — not standard OpenStack.
Requires Platform9 API token from `https://<pf9_fqdn>/keystone/v3/auth/tokens`.

### Create Neutron router with external gateway
```python
router = conn.network.create_router(
    name="<ROUTER_NAME>",
    external_gateway_info={"network_id": "<EXTERNAL_NET_ID>"},
)
conn.network.add_interface_to_router(router.id, subnet_id="<INTERNAL_SUBNET_ID>")
```

---

## Output Format

Return the complete script as a fenced code block with language tag:

```python
# Usage: python script.py --project <project_name>
# Requires: pip install openstacksdk
# Env vars: OS_AUTH_URL, OS_PROJECT_NAME, OS_USERNAME, OS_PASSWORD, OS_DOMAIN_NAME
...
```

For Bash:
```bash
#!/usr/bin/env bash
# Usage: ./script.sh
# Requires: curl, jq
# Env vars: OS_AUTH_URL, OS_PROJECT_NAME, OS_USERNAME, OS_PASSWORD, OS_DOMAIN_NAME
...
```

After the code block, add a brief "**Notes:**" section covering:
- Any non-obvious dependency or permission requirement
- Known Platform9-specific differences from upstream OpenStack
- Version caveats (if the task requires a specific OpenStack API microversion)
