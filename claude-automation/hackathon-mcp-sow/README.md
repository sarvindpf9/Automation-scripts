# Platform9 PCD MCP Server

An MCP server that gives Claude Desktop six tools for Platform9 Private Cloud Director engagements — procedure documents, engagement trackers, document editing, SOW parsing, technical Q&A, and automation scripts. Works with Claude Desktop and Claude Code. No coding required to use.

---

## Quick Start — First Result in 5 Steps

This section is self-contained. Follow it top to bottom and you will have a working tool in about 10 minutes.

### Step 1 — Install

```bash
git clone <repo-url>
cd hackathon-mcp-sow

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Smoke-test (no API key needed):

```bash
python test_manual.py --direct
```

Expected — three green ticks, no errors:

```
  ✓  docs_reader: read 8 files (88,462 chars total)
  ✓  issues_tracker: 4 sheets → output/TestCustomer/TestCustomer_issues_tracker.xlsx
  ✓  engagement_tracker: 3 sheets → output/TestCustomer/TestCustomer_engagement_tracker.xlsx
```

If you see errors here, do not proceed — check that Python 3.12+ is active and `pip install` completed without failures.

### Step 2 — Drop your SOW PDF into `SOW-docs/`

```bash
cp /path/to/YourCustomer_PF9_PCD_SOW.pdf SOW-docs/
```

That is the only file you need to place manually. Everything else (reference docs, output directory) is already in place.

### Step 3 — Get your repo path

Run this inside the cloned repo and copy the output — you will need it in Step 4:

```bash
pwd
# example output: /Users/you/hackathon-mcp-sow
```

### Step 4 — Register with Claude Desktop

Open (or create) `~/Library/Application Support/Claude/claude_desktop_config.json`.
Replace `<REPO_PATH>` in both places with the path from Step 3, and insert your Anthropic API key:

```json
{
  "mcpServers": {
    "pcd-assistant": {
      "command": "<REPO_PATH>/.venv/bin/python",
      "args": ["-m", "sow_mcp.server"],
      "cwd": "<REPO_PATH>",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

> The API key **must** be in the `"env"` block. Shell environment variables are not inherited by Claude Desktop on macOS.

Quit Claude Desktop fully with **⌘Q** (not just close the window) and reopen it.

### Step 5 — Generate your first document

Open Claude Desktop, start a new conversation, and type:

```
Generate a Day 0 / Day 1 / Day 2 procedure document for <YourCustomer>.
```

Claude will call `build_procedure_doc` automatically. When it finishes, open the PDF:

```bash
open output/<YourCustomer>/<YourCustomer>_procedure.pdf
```

That is it. The remaining sections explain all six tools and their options in detail.

---

## What it does

| Tool | What you provide | What you get |
|---|---|---|
| `parse_sow` | SOW PDF in `SOW-docs/` | Structured JSON of objectives, scope, deliverables, assumptions |
| `build_procedure_doc` | SOW in `SOW-docs/` + reference docs in `docs/` | Day 0 / Day 1 / Day 2 procedure as Markdown + PDF in `output/` |
| `edit_procedure_doc` | Plain-English instructions + existing procedure in `output/` | Updated Markdown + PDF with sections added, removed, or rewritten |
| `generate_tracker` | SOW in `SOW-docs/` or meeting notes text | Excel tracker (SOW deliverables or issues/bugs) in `output/` |
| `answer_query` | A question | Cited answer drawn from live Platform9, OpenStack, and K8s docs |
| `build_automation` | A task description | Working Python or Bash script for OpenStack / PCD operations |

---

## File Directories

```
hackathon-mcp-sow/
├── SOW-docs/          ← INPUT  — drop customer SOW PDFs here before running any SOW tool
├── docs/              ← INPUT  — Platform9 reference docs (shipped; add customer docs alongside)
└── output/            ← OUTPUT — all generated files land here automatically (gitignored)
    └── <customer>/
        ├── <customer>_procedure.md
        ├── <customer>_procedure.pdf
        ├── <customer>_issues_tracker.xlsx
        └── <customer>_engagement_tracker.xlsx
```

### `SOW-docs/` — customer SOW input

All SOW tools read from here. Accepted formats: `.pdf`, `.docx`, `.doc`.

| Condition | Behaviour |
|---|---|
| Exactly one file, no name given in prompt | Auto-selected — no prompt |
| Multiple files, no name given | Tool lists all files and asks which one to use |
| Filename or partial name given (e.g. `"ValorC3"`) | Matched case-insensitively; prompts if ambiguous |
| No files present | Tool explains what to do and stops |

### `docs/` — Platform9 reference docs

Used by `build_procedure_doc` as synthesis context. The following files are included by default:

| File | Content |
|---|---|
| `Canary_PCD SaaS_Solution-doc.pdf` | PCD SaaS solution design — Canary environment |
| `PCD_Host-prep_and_onboarding_with_roles_v2.pdf` | Host preparation and onboarding with roles |
| `MaaS_deployment_Guide.pdf` | MaaS deployment guide |
| `Setup_live_migration_network.pdf` | Live migration network setup |
| `vjailbreak_deployment_migration-doc.pdf` | vJailbreak VM migration guide |
| `VM-Image_creation_recommendation-v1.pdf` | VM image creation recommendations |
| `PCD-onboarding-confluence-doc.pdf` | PCD-V SA onboarding MOP |
| `Commvault-installation-doc.pdf` | Commvault backup integration |

Add any customer-specific architecture docs or additional guides alongside these.

### `output/` — generated artifacts

Created automatically on first use; gitignored. Re-running a tool for the same customer overwrites the previous file. Open files from Finder or:

```bash
open output/Acme_Corp/Acme_Corp_procedure.pdf
open output/NTT/NTT_issues_tracker.xlsx
```

---

## Connecting to Claude Desktop

### Verify the server is connected

After restarting Claude Desktop, open a new conversation and click the **plug icon** (🔌) or **hammer icon** (🔨) at the bottom-left of the message box. You should see:

```
pcd-assistant
  parse_sow
  build_procedure_doc
  edit_procedure_doc
  generate_tracker
  answer_query
  build_automation
```

If the server name does not appear, see [Troubleshooting](#troubleshooting).

### How tool calls work

You never call tools by name. Type your request in plain English — Claude picks the right tool automatically, shows a collapsible tool-use card, and prints the result inline.

---

## Tools — Detailed Usage

### `parse_sow` — Extract structured data from a SOW

Reads a SOW PDF from `SOW-docs/` and returns a structured JSON document (`SowDocument`) containing objectives, scope, deliverables, assumptions, acceptance criteria, out-of-scope items, and VM migration details.

**Before calling:** copy the SOW PDF into `SOW-docs/`.

**Example prompts:**

```
Parse the ValorC3 SOW.
```
```
Extract the deliverables and scope from the NTT SOW PDF.
```

**What the tool extracts** (sections absent from the SOW are omitted — nothing is invented):

| Field | Source in SOW |
|---|---|
| `objectives` | Objectives / Project Objectives |
| `scope_sections` | Scope of Work — one entry per phase |
| `deliverables` | Deliverables — linked to scope sections by ID |
| `assumptions` | Assumptions |
| `acceptance_criteria` | Acceptance Criteria / Definition of Done |
| `out_of_scope` | Out of Scope / Exclusions |
| `vm_migrations` | VM Migrations / Workload Migration Scope |

The returned JSON can be passed directly to `generate_tracker` (`tracker_type="sow"`) or used as input context for other tools.

---

### `build_procedure_doc` — Generate a Day 0 / Day 1 / Day 2 procedure document

Synthesises a full deployment procedure document from the reference docs in `docs/` and the customer SOW in `SOW-docs/`.

**Before calling:** copy the SOW PDF into `SOW-docs/`.

**Example prompts:**

```
Generate a Day 0 / Day 1 / Day 2 procedure document for the NTT engagement.
```
```
Build a deployment procedure doc for ValorC3 using the ValorC3 SOW.
```
```
Generate a procedure document for Acme Corp.
```

**Output files:**

```
output/Acme_Corp/Acme_Corp_procedure.md    ← editable Markdown
output/Acme_Corp/Acme_Corp_procedure.pdf   ← formatted PDF, ready to share
```

The PDF is structured as: title page → Day 0 (infrastructure assessment, network/storage planning, integration planning) → Day 1 (PCD install, storage, network, monitoring, SSO integrations) → Day 2 (VM migration, monitoring, backup, runbooks, knowledge transfer). Environment-specific values not found in the source docs appear as `<PLACEHOLDER>` tokens.

---

### `edit_procedure_doc` — Edit an existing procedure document

Applies natural-language edit instructions to a procedure document that already exists in `output/`. Supports adding, removing, and rewriting individual sections. Unchanged sections are preserved exactly — only the targeted sections involve a Claude API call.

**Before calling:** `build_procedure_doc` must have been run for the same customer first.

**Supported edit types (can be combined in one instruction):**

| Edit type | Example instruction |
|---|---|
| Remove a section | `"Remove the MaaS Setup section"` |
| Add a section | `"Add a Live Migration Network section after Network Integration with OVN tunnel configuration steps"` |
| Rewrite a section | `"Rewrite the Storage Integration section for Pure Storage iSCSI instead of NetApp"` |
| Combined | `"Remove MaaS Setup and add a Bare Metal Provisioning section after PCD Installation"` |

**Example prompts:**

```
Remove the MaaS Setup & Hypervisor Onboarding section from the ValorC3 procedure doc.
```
```
Add a section on live migration network configuration with VxLAN provider network setup
and OVN tunnel endpoint steps to the NTT procedure doc. Place it after Network Integration.
```
```
Rewrite the Storage Integration section of the ValorC3 doc for Pure Storage iSCSI.
```

**Output:** overwrites the existing `.md` and `.pdf` in `output/<customer>/`.

**How it works internally:** A cheap planning call sends only the section headings to Claude and gets back a JSON list of operations. Removals are applied in pure Python. Each add or rewrite sends only that single section to Claude — no full-document round-trips, no token waste, no output-length limits.

---

### `generate_tracker` — Generate an Excel engagement tracker

Produces an `.xlsx` workbook for either open issues/bugs (`tracker_type="issues"`) or SOW deliverables (`tracker_type="sow"`).

**Issues tracker** — paste meeting notes or a Jira export directly into the prompt:

```
Create an issues tracker for NTT with these items from today's sync:
- SSO with ADFS still pending, ECS-171 raised
- Commvault backup integration not started, high priority
- Pure Storage production integration blocked — wiring issues
- VMHA stuck in waiting state, bug PCD-5795 filed
```

**Output:** `output/NTT/NTT_issues_tracker.xlsx` — four sheets:
- **Summary** — counts by status and priority
- **Issue_tracker** — full issue list with owner, priority, status, notes
- **Bug_reported** — bugs filtered from the issue list
- **Open Actions** — action items extracted from notes

Status colour-coding: Done (green), In-discussion (blue), Not started (yellow), Engineering (orange), Blocked (red). Priority: High (red), Medium (orange), Low (green).

**SOW deliverables tracker** — reads the SOW from `SOW-docs/`:

```
Generate a SOW deliverables tracker for ValorC3.
```
```
Generate a SOW tracker for NTT using NTT-SOW.pdf.
```

**Output:** `output/ValorC3/ValorC3_engagement_tracker.xlsx` — one sheet per scope section plus an All Deliverables sheet.

**Combined** — generates both in one call:

```
Generate both the issues tracker and SOW tracker for NTT.
```

---

### `answer_query` — Answer a PCD / OpenStack / Kubernetes question

Fetches live content from Platform9 docs, OpenStack Epoxy API references, and kubernetes.io, then answers with citations.

**Example prompts:**

```
What are the prerequisites for installing Platform9 PCD in self-hosted mode?
```
```
How do I configure a separate live migration network in PCD?
```
```
VMHA is stuck in waiting state after adding hosts. How do I fix it?
```
```
What OpenStack API call creates a Neutron router with an external gateway?
```
```
How do I onboard a hypervisor host using the resmgr API?
```

Every answer ends with a **References:** block listing the source URLs used.

| Keywords in your question | Docs fetched |
|---|---|
| `kubernetes`, `k8s` | Platform9 K8s overview + kubernetes.io |
| `troubleshoot`, `error`, `issue`, `fix` | platform9.com/kb/pcd-ts + platform9.com/kb/pcd |
| `openstack`, `nova`, `neutron`, `cinder` | docs.openstack.org/epoxy |
| anything else | docs.platform9.com/private-cloud-director |

---

### `build_automation` — Generate a working automation script

Produces a complete Python or Bash script for any OpenStack or Platform9 PCD operation, grounded in the Platform9 and OpenStack API references.

**Example prompts:**

```
Write a Python script to list all Nova instances across all projects with their status, host, and IP.
```
```
Write a Bash script to snapshot all Cinder volumes in a project before a maintenance window.
```
```
Generate a Python script to create a Neutron security group with inbound HTTP and HTTPS rules.
```
```
Write a Python script to migrate all VMs off a compute host for maintenance.
```

Every script includes:
- A `# Usage:` block at the top
- Authentication via `OS_AUTH_URL`, `OS_USERNAME`, `OS_PASSWORD`, `OS_PROJECT_NAME`, `OS_DOMAIN_NAME` — never hardcoded
- Error handling, pagination for large result sets, and a `--dry-run` flag on destructive operations
- A **Notes:** section covering any Platform9-specific deviations from upstream OpenStack

---

## Testing the server manually

`test_manual.py` verifies the full stack before connecting Claude Desktop. Run it after any code change or after moving the repo.

```bash
# No API key — tests file I/O, doc reading, Excel generation
python test_manual.py --direct

# With API key — also tests answer_query, build_automation, procedure_doc
ANTHROPIC_API_KEY=sk-ant-... python test_manual.py --direct

# MCP wire format — spawns the real server over stdin/stdout (same as Claude Desktop)
python test_manual.py --mcp

# Both modes
ANTHROPIC_API_KEY=sk-ant-... python test_manual.py --all
```

Expected output without an API key:

```
ANTHROPIC_API_KEY : not set — LLM tools will be skipped
Python            : /path/to/.venv/bin/python3.14
Working directory : /path/to/hackathon-mcp-sow

Direct mode — calling Python functions without MCP overhead
────────────────────────────────────────────────────────────
  ✓  docs_reader: read 8 files (88,462 chars total)
  ✓  issues_tracker: 4 sheets → output/TestCustomer/TestCustomer_issues_tracker.xlsx
  ✓  engagement_tracker: 3 sheets → output/TestCustomer/TestCustomer_engagement_tracker.xlsx

  (skipping LLM tools — ANTHROPIC_API_KEY not set)

MCP protocol mode — JSON-RPC 2.0 over stdio (real wire format)
────────────────────────────────────────────────────────────
  ✓  initialize: protocol 2024-11-05, server 'pcd-mcp-server'
  ✓  tools/list: ['parse_sow', 'build_procedure_doc', 'edit_procedure_doc',
                  'generate_tracker', 'answer_query', 'build_automation']
  ✓  tools/call generate_tracker: output/MCPTest/MCPTest_issues_tracker.xlsx
```

---

## Troubleshooting

**Server does not appear in Claude Desktop**

Quit Claude Desktop fully with **⌘Q** (not just close the window) and reopen it. If it still does not appear, open `claude_desktop_config.json` and check:

- `"command"` points to `.venv/bin/python` inside the repo — not the system `python3`
- Both `<REPO_PATH>` placeholders are replaced with the absolute path (no trailing slash)
- The JSON is valid — a trailing comma or missing brace silently breaks the entire config

Check MCP server logs in Claude Desktop: **Settings → Developer → MCP Logs**.

**`ANTHROPIC_API_KEY` not found during tool calls**

The key must be in the `"env"` block inside `claude_desktop_config.json`. Shell environment variables are not inherited by Claude Desktop on macOS. Restart Claude Desktop fully after adding the key.

**SOW file not found**

The server reads SOW files from `SOW-docs/` inside the repo directory. It cannot access files uploaded through Claude Desktop's attachment button — that path (`/mnt/user-data/uploads/...`) is not reachable by the MCP subprocess. Copy the PDF manually:

```bash
cp /path/to/your.pdf SOW-docs/
```

**`docs_dir does not exist` warning**

All paths are resolved relative to the server's install location, not the process working directory. If you see this warning, confirm that `docs/` exists inside the repo and contains at least one `.pdf` or `.docx` file.

**PDFs produce empty or very short text**

Some PDFs are image-only scans — `pdfplumber` cannot extract text from them without an OCR layer. Convert to a searchable PDF first:

```bash
# requires ocrmypdf
ocrmypdf input.pdf input_ocr.pdf
```

Or copy the content into a `.docx` file and place it in `docs/`.

**PDF output has garbled or missing characters**

The PDF renderer uses Helvetica (latin-1 only). Common Unicode characters — em-dashes, curly quotes, bullets, non-breaking spaces — are automatically substituted before rendering. Any character outside that mapping is replaced with `?`. The `.md` file always has the full-fidelity content. To produce a Unicode-clean PDF from the Markdown:

```bash
pandoc output/Acme_Corp/Acme_Corp_procedure.md -o Acme_Corp_procedure.pdf
```

**`edit_procedure_doc` says the document does not exist**

`edit_procedure_doc` reads from `output/<customer_name>/<customer_name>_procedure.md`. Run `build_procedure_doc` for that customer first, then edit.

**Tool call hangs or times out**

`answer_query` and `build_automation` fetch live web pages with a 10-second timeout per URL. A slow or unreachable Platform9/OpenStack docs site causes a delay but not a crash — the tool falls back to Claude's training data and notes the limitation in its answer. Check your network connection if all queries time out consistently.
