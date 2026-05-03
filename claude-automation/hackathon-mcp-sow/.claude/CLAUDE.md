# CLAUDE.md — Platform9 PCD MCP Server

## Purpose

A generic MCP server for Platform9 Private Cloud Director (PCD) engagements.
Any Solution Architect with an Anthropic API key and access to this repo can use it.

**What it does:**

| Tool | Input | What it produces |
|---|---|---|
| `parse_sow` | SOW PDF from `SOW-docs/` | Structured `SowDocument` JSON |
| `build_procedure_doc` | `SOW-docs/` + `docs/` | Day 0 / Day 1 / Day 2 procedure (Markdown + PDF) in `output/<customer>/` |
| `edit_procedure_doc` | Existing procedure in `output/<customer>/` | Updated Markdown + PDF (section-scoped edits) |
| `generate_tracker` | SOW PDF from `SOW-docs/` or issue text | Excel tracker in `output/<customer>/` |
| `answer_query` | Question string | Cited answer from live Platform9 / OpenStack docs |
| `build_automation` | Task description | Working Python or Bash script |

---

## Quick Start (for SAs)

```bash
git clone <repo>
cd hackathon-mcp-sow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# INPUT — customer SOW PDFs
cp /path/to/CustomerName_PF9_PCD_SOW.pdf SOW-docs/

# INPUT — Platform9 reference docs (already included; add customer-specific docs here)
cp /path/to/customer-architecture.pdf docs/

# OUTPUT — generated files land here automatically (gitignored)
# output/<customer_name>/<customer_name>_procedure.md
# output/<customer_name>/<customer_name>_procedure.pdf
# output/<customer_name>/<customer_name>_issues_tracker.xlsx
# output/<customer_name>/<customer_name>_engagement_tracker.xlsx

# Add to Claude Desktop config (see "Running the Server" below)
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running the Server

Add to `~/.config/Claude/claude_desktop_config.json` (Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pcd-assistant": {
      "command": "/path/to/hackathon-mcp-sow/.venv/bin/python",
      "args": ["-m", "sow_mcp.server"],
      "cwd": "/path/to/hackathon-mcp-sow",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Restart Claude Desktop. All six tools appear automatically.

---

## Tool Usage Examples

```
# ── Inputs required before running any SOW tool ──────────────────────────────
# SOW PDFs   → SOW-docs/   (parse_sow, generate_tracker, build_procedure_doc read here)
# Ref docs   → docs/       (build_procedure_doc reads here for background context)
# All output → output/<customer_name>/   (created automatically, gitignored)

# Parse a SOW — file must be in SOW-docs/
parse_sow("ValorC3_PF9_PCD_SOW.pdf")   # exact filename
parse_sow("ValorC3")                    # partial name — resolves if unambiguous
parse_sow()                             # auto-select when exactly one file present

# Generate SOW deliverables tracker — reads SOW from SOW-docs/
# Output: output/ValorC3/ValorC3_engagement_tracker.xlsx
generate_tracker("ValorC3", tracker_type="sow", sow_filename="ValorC3_PF9_PCD_SOW.pdf")
generate_tracker("ValorC3", tracker_type="sow")   # auto-select or prompted

# Generate issues tracker from weekly sync notes
# Output: output/Acme_Corp/Acme_Corp_issues_tracker.xlsx
generate_tracker("Acme Corp", "SSO with ADFS pending ECS-171, Commvault not started...", tracker_type="issues")

# Generate a full Day0/Day1/Day2 procedure doc
# Input:  SOW-docs/<sow>.pdf  +  docs/*.pdf / *.docx
# Output: output/ValorC3/ValorC3_procedure.md  +  ValorC3_procedure.pdf
build_procedure_doc("ValorC3", sow_filename="ValorC3_PF9_PCD_SOW.pdf")
build_procedure_doc("ValorC3")   # auto-selects SOW if exactly one present

# Edit an existing procedure doc with natural-language instructions
# Input:  output/ValorC3/ValorC3_procedure.md  (must exist — run build_procedure_doc first)
# Output: overwrites output/ValorC3/ValorC3_procedure.md + ValorC3_procedure.pdf
edit_procedure_doc("ValorC3", "Remove the MaaS Setup section and add a Live Migration Network section after Network Integration")
edit_procedure_doc("ValorC3", "Rewrite the Storage Integration section for Pure Storage iSCSI")

# Answer a technical question (no file input required)
answer_query("How do I configure live migration network separation in PCD?")

# Generate automation (no file input required)
build_automation("snapshot all Cinder volumes in a project", language="python")
build_automation("list all VMs across all projects", language="bash")
```

---

## File I/O Directories

### INPUT — `SOW-docs/`

Drop customer SOW PDFs (`.pdf`, `.docx`, `.doc`) here before calling any SOW tool.
Read by: `parse_sow`, `generate_tracker` (tracker_type sow/combined), `build_procedure_doc`.

| Condition | Behaviour |
|---|---|
| Exactly one file, no name given | Auto-selected |
| Multiple files, no name given | Tool lists files and asks user to pick |
| Filename (exact or partial) given | Matched case-insensitively; prompts if ambiguous |
| No files present | Tool returns instructions to add the PDF and stops |

### INPUT — `docs/`

Platform9 reference docs used by `build_procedure_doc` as synthesis context.
Supported formats: `.pdf`, `.docx`. Add customer-specific docs alongside the defaults.

Included by default:
- `Canary_PCD SaaS_Solution-doc.pdf` — PCD SaaS solution design (Canary environment)
- `PCD_Host-prep_and_onboarding_with_roles_v2.pdf` — host preparation and onboarding with roles
- `MaaS_deployment_Guide.pdf` — MaaS deployment guide
- `Setup_live_migration_network.pdf` — live migration network setup
- `vjailbreak_deployment_migration-doc.pdf` — vJailbreak VM migration guide
- `VM-Image_creation_recommendation-v1.pdf` — VM image creation recommendations
- `PCD-onboarding-confluence-doc.pdf` — PCD-V SA onboarding MOP
- `Commvault-installation-doc.pdf` — Commvault backup integration

### OUTPUT — `output/<customer_name>/`

All generated artifacts. Created automatically; gitignored. Re-running a tool
overwrites the previous file for the same customer.

| File | Produced by |
|---|---|
| `<customer>_procedure.md` | `build_procedure_doc`, `edit_procedure_doc` |
| `<customer>_procedure.pdf` | `build_procedure_doc`, `edit_procedure_doc` |
| `<customer>_issues_tracker.xlsx` | `generate_tracker` (tracker_type=issues/combined) |
| `<customer>_engagement_tracker.xlsx` | `generate_tracker` (tracker_type=sow/combined) |

`edit_procedure_doc` reads the existing `_procedure.md` from this directory and
overwrites both the `.md` and `.pdf` in place.

---

## Reference URLs

The server fetches live content from these sources to answer queries and build automation:

**Platform9 Documentation:**
- https://docs.platform9.com/private-cloud-director
- https://docs.platform9.com/private-cloud-director/getting-started/self-hosted
- https://docs.platform9.com/private-cloud-director/kubernetes-clusters/k8s-overview
- https://platform9.com/kb/pcd-ts  _(troubleshooting KB)_
- https://platform9.com/kb/pcd
- https://docs.platform9.com/api-docs  _(Platform9 REST API)_

**OpenStack (Epoxy and above):**
- https://docs.openstack.org/epoxy/
- https://docs.openstack.org/api-ref/compute/
- https://docs.openstack.org/api-ref/network/v2/
- https://docs.openstack.org/api-ref/block-storage/v3/
- https://docs.openstack.org/api-ref/identity/v3/
- https://docs.openstack.org/api-ref/image/v2/

**Kubernetes:**
- https://kubernetes.io/docs/home/

---

## Skills

| Skill | File | Triggers |
|---|---|---|
| `readme-writer` | `.claude/skills/readme-writer/SKILL.md` | write readme, update readme, document tool, README for MCP server, procedure.md formatting |
| `sow-reader` | `.claude/skills/sow-reader/SKILL.md` | `parse_sow`, SOW PDF uploaded, extract SOW sections |
| `engagement-tracker` | `.claude/skills/engagement-tracker/SKILL.md` | `generate_tracker`, issues/bugs/SOW tracker |
| `automation-builder` | `.claude/skills/automation-builder/SKILL.md` | `build_automation`, OpenStack/PCD script generation |
| `pdf-renderer` | `.claude/skills/pdf-renderer/SKILL.md` | modify PDF renderer, change theme/colours/layout, add element type, debug PDF formatting |

---

## Project Layout

```
hackathon-mcp-sow/
├── SOW-docs/                    ← INPUT: customer SOW PDFs (.pdf/.docx/.doc)
│                                    parse_sow, generate_tracker, build_procedure_doc read here
├── docs/                        ← INPUT: Platform9 reference docs (architecture, MaaS, vJailbreak, etc.)
│                                    build_procedure_doc uses these as synthesis context
├── output/                      ← OUTPUT: all generated artifacts (gitignored)
│   └── <customer_name>/
│       ├── <customer>_procedure.md          ← build_procedure_doc, edit_procedure_doc
│       ├── <customer>_procedure.pdf         ← build_procedure_doc, edit_procedure_doc
│       ├── <customer>_issues_tracker.xlsx   ← generate_tracker (issues/combined)
│       └── <customer>_engagement_tracker.xlsx ← generate_tracker (sow/combined)
├── sow_mcp/
│   ├── server.py                ← 6 MCP tools
│   ├── docs_reader.py           ← PDF/DOCX text extraction
│   ├── models.py                ← SowDocument, DocChunk dataclasses
│   ├── output_writer.py         ← all file I/O anchored to package root
│   ├── parser.py                ← SOW-specific LLM extractor (internal)
│   ├── generators/
│   │   ├── procedure_doc.py     ← Day0/Day1/Day2 generation + section-aware editing + PDF renderer
│   │   ├── engagement_tracker.py← SOW deliverables tracker (openpyxl)
│   │   ├── issues_tracker.py    ← Issues/bugs tracker (openpyxl)
│   │   ├── query_answerer.py    ← web fetch + Claude Q&A
│   │   └── automation_builder.py← API-grounded script generation
│   └── templates/
│       └── excel_styles.py      ← all Excel formatting constants
├── tests/
├── requirements.txt
└── pyproject.toml
```

---

## Platform9 PCD Domain Context

**Product:** Platform9 Private Cloud Director (PCD) — OpenStack Epoxy+, SaaS management
plane, OVN ML2 networking, Ceph RBD / external storage (NetApp, Pure Storage).

**Delivery model:** White Glove — Platform9 architects, builds, and operationalises
end-to-end, then hands off to the customer operations team.

**Typical engagement phases:**
1. Canary — staging/validation environment (≤4 hypervisors)
2. Production — full datacenter deployment (10–250+ hypervisors)
3. MaaS — bare-metal provisioning via ILO/IPMI network boot
4. Migration — VMware to PCD VM migration using vJailbreak
5. Training & Handover

**Common integrations:** NetApp (FC/NFS), Pure Storage, Commvault, Veeam, Nagios,
Checkmk, Prometheus, Infoblox/BlueCat (IPAM), Microsoft AD (LDAP/SAML), Okta.

---

## Coding Standards

- Python 3.12+, PEP8, type hints on all function signatures, `black`-compatible
- No bare `except` — catch specific exceptions with context in log messages
- MCP tool handlers are thin: validate input, call generator, return result
- All file I/O via `OutputWriter` — no scattered `open()` calls
- Excel formatting defined in `templates/excel_styles.py` — no inline styles
- Prompt caching (`cache_control: ephemeral`) on large input blocks (docs text, SOW text, section bodies)
- `edit_procedure_doc` uses two phases: one cheap planning call (headings only) + one targeted call per changed section — no full-document round-trips

---

## Operational Rules

1. **Scope discipline**: answer what is asked; do not expand scope without invitation
2. **No invented values**: use `<PLACEHOLDER>` for env-specific unknowns; never invent IPs, names, CIDRs
3. **Ambiguity**: ask one focused question before producing output when intent is unclear
4. **Propose, don't apply**: for schema or output format changes, describe the change first
5. **Flag uncertainty**: if unsure about an OpenStack/PCD version-specific behaviour, say so in one sentence
