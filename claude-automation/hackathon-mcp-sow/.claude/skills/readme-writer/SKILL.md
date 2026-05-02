---
name: readme-writer
description: "Use this skill when writing or updating README.md for this MCP server or its generated documents (procedure.md, tracker). Covers: tool-suite README structure, Quick Start patterns, I/O directory documentation, procedure.md formatting rules, and pitfalls observed during generation and editing."
---

# README and Procedure Document Writer Skill

## Trigger

Use this skill when:
- Writing or updating `README.md` for the MCP server or any sub-component
- Writing documentation that references `SOW-docs/`, `docs/`, or `output/` directories
- Adding a new tool to the server and documenting it
- Generating or editing `*_procedure.md` files via `build_procedure_doc` or `edit_procedure_doc`

---

## Part 1 — README Files for Tool Suites

### Guiding Principle

A new SA picking up this repo must be able to produce their first document within 10 minutes without asking anyone for help. Every README must answer: "What do I put where, and what do I get back?"

---

### Section Order (canonical)

```
1. Title + one-line description
2. Quick Start              ← self-contained, produces a visible result
3. What it does             ← table of tools/features with input and output columns
4. File Directories         ← every input and output directory documented
5. Setup / Registration     ← detailed install and config steps
6. Tools — Detailed Usage   ← one subsection per tool
7. Testing                  ← how to verify it works
8. Troubleshooting          ← actual errors users will hit, not hypothetical ones
```

Never bury Quick Start after Setup. A new user reads top-to-bottom and abandons the doc if they have to page past install instructions to understand what the tool even does.

---

### Quick Start Rules

The Quick Start section must be **fully self-contained** — a reader must be able to follow it without reading any other section.

Required elements:
1. **Install** — exact commands (clone, venv, pip, smoke-test with expected output)
2. **Input** — exact `cp` command showing where to put the customer file
3. **Path** — tell the user to run `pwd` and copy the result (needed for config)
4. **Config** — complete JSON block with `<REPO_PATH>` as the only placeholder; instruct the user to substitute it
5. **Restart** — explicit "quit with ⌘Q, not just close" instruction
6. **First result** — a single example sentence to type into Claude, and the `open` command to view the output

Do not split any of these across sections. If a step requires something from a previous step (e.g. the path from Step 3 is needed in Step 4), say so explicitly: "Replace `<REPO_PATH>` with the path from Step 3."

---

### What it Does — Table Format

Always include an **Input** column, not just a description. Users need to know what to prepare before running a tool.

```markdown
| Tool | What you provide | What you get |
|---|---|---|
| `tool_name` | Input source (file location, text, etc.) | Output artifact and its location |
```

Bad (no input column):
```markdown
| Tool | What it produces |
|---|---|
| `build_procedure_doc` | Day 0/1/2 procedure document |
```

Good:
```markdown
| Tool | What you provide | What you get |
|---|---|---|
| `build_procedure_doc` | SOW in `SOW-docs/` + reference docs in `docs/` | Procedure Markdown + PDF in `output/<customer>/` |
```

---

### File Directories — Documentation Pattern

Every directory that a user must interact with needs three things:
1. Its purpose and which tools read/write it
2. Behaviour table for non-obvious cases (e.g. what happens with 0, 1, or multiple files)
3. The exact `cp` command needed to populate it

**Template for an input directory:**

```markdown
### `SOW-docs/` — customer SOW input

Drop files here before calling any SOW tool. Accepted: `.pdf`, `.docx`, `.doc`.

| Condition | Behaviour |
|---|---|
| Exactly one file, no name given | Auto-selected |
| Multiple files, no name given | Tool lists files and asks which to use |
| Filename or partial name given | Matched case-insensitively; prompts if ambiguous |
| No files present | Tool explains what to do and stops |
```

**Template for an output directory:**

```markdown
### `output/<customer_name>/` — generated artifacts

Created automatically; gitignored. Re-running overwrites the previous file.

| File | Produced by |
|---|---|
| `<customer>_procedure.md` | `build_procedure_doc`, `edit_procedure_doc` |
| `<customer>_procedure.pdf` | `build_procedure_doc`, `edit_procedure_doc` |
```

---

### Tool Documentation — Per-Tool Pattern

Each tool section must include all of the following:

```markdown
### `tool_name` — Short description

One-sentence explanation of what the tool does and when to use it.

**Before calling:** prerequisite the user must complete first (e.g. copy file to SOW-docs/).

**Example prompts:**

```
Plain-English prompt that will trigger this tool.
```
```
Second example with a different use case or option.
```

**Output files:**

```
output/<customer>/<customer>_output_file.ext   ← what it is
```

**How it works** (only for non-obvious internal behaviour):
Brief explanation of the mechanism — e.g. "sends only section headings to Claude, not the full document".
```

---

### Troubleshooting — Content Rules

Include only errors that **actually happened** during development or testing. Never invent hypothetical failures.

Each entry must:
- State the symptom as a user would see it (bold heading)
- Give the exact cause in one sentence
- Give the fix as a concrete command or action

Example of a real observed error to document:
```
**SOW file not found**

The server reads from `SOW-docs/` inside the repo. Claude Desktop's file upload button
produces a path (`/mnt/user-data/uploads/...`) that is not accessible to the MCP subprocess.

cp /path/to/your.pdf SOW-docs/
```

---

### Consistency Rules

1. **Tool count** — if the server exposes N tools, every mention of the count must match: the overview, the "verify connected" section, the test output, and the project layout comment in code.
2. **Filenames** — use the actual current filename, not a description. If files were renamed, update every reference.
3. **Code block language tags** — always set: ` ```bash `, ` ```json `, ` ```ini `, ` ```yaml `. Never use ` ``` ` alone for commands.
4. **Placeholders** — use `<SCREAMING_SNAKE_CASE>` consistently. Never mix `<placeholder>`, `{placeholder}`, and `$PLACEHOLDER` in the same document.
5. **Horizontal rules** — use `---` only as a top-level section separator, not between subsections.
6. **Callouts** — use `>` blockquotes only for warnings the user must not miss (e.g. "The API key must be in the env block"). Do not use them for general information.

---

## Part 2 — Procedure Document Generation (`*_procedure.md`)

These are patterns and pitfalls observed when generating and editing Day 0 / Day 1 / Day 2 deployment procedure documents via `build_procedure_doc` and `edit_procedure_doc`.

---

### Document Structure Contract

The generated procedure document follows a strict H1/H2 hierarchy:

```
# <Title>              ← H1: document title (one per doc)
## Customer: ...       ← H2: header metadata
## Prepared by: ...
## Date: ...

# Day 0 — ...          ← H1: one per day block
## 1. Section Title    ← H2: numbered sections within a day
### Overview / Prerequisites / Procedure / Verification / Rollback   ← H3: subsections
```

**Never** place H3 or lower headings at H2 level. **Never** renumber Day-block H1s. The parser splits at H1/H2 only — H3 and below live inside the parent H2's body.

---

### Procedure Section Subsections

| Day | Required subsections | Notes |
|---|---|---|
| Day 0 | Overview, Prerequisites Checklist, Steps | No Rollback |
| Day 1 | Prerequisites, Procedure, Verification, Rollback | Rollback is mandatory even if irreversible — state the impact |
| Day 2 | Overview, Prerequisites, Procedure, Verification | No Rollback |

If true rollback is not possible for a Day 1 section, write:
```
### Rollback
> **True rollback is not possible** once this step completes. Impact: [describe].
```
Never omit the Rollback subsection from a Day 1 section.

---

### Placeholder Convention

Use `<PLACEHOLDER>` (uppercase, angle brackets) for any value that is environment-specific and not found in the reference docs or SOW. Never invent plausible-sounding values.

```markdown
Good: Configure the cluster name: `<CLUSTER_NAME>`
Bad:  Configure the cluster name: `pcd-prod-cluster`
```

Specific placeholder names are better than generic ones:
```
<PLACEHOLDER>            ← acceptable but vague
<PCD_CLUSTER_NAME>       ← preferred
<NFS_EXPORT_PATH>        ← preferred
```

---

### Code Fence Pitfall — Section Parser Corruption

**Symptom:** After running `edit_procedure_doc` multiple times, sections appear in the wrong place, content from one section lands inside another's code block, or Day 2 sections disappear.

**Root cause:** Generated section bodies often contain bash scripts or config files with `##` comment lines:
```bash
## This is a bash section heading comment
# Or a single-hash comment
```

If the Markdown parser is not fence-aware, it sees `## ` and incorrectly treats it as an H2 section boundary, splitting the section mid-code-block on every subsequent edit pass.

**Fix already in place:** `_parse_sections()` in `procedure_doc.py` tracks ```` ``` ```` and `~~~` fence state and suppresses heading detection inside fenced blocks. Do not bypass this by stripping code fences from generated content.

**Prevention rule for `_SECTION_SYSTEM` prompt:** Do not instruct Claude to omit code blocks. The fence-awareness in the parser handles them. Removing code fences would make the procedure less useful.

---

### Section Numbering After Edits

After any `add` or `remove` operation, section numbers within a day block can become inconsistent (e.g. `1, 3, 4` after removing section 2, or duplicate `3. New` alongside `3. Storage`).

**Fix already in place:** `_renumber_day_sections()` runs after all ops in a single edit call and re-assigns sequential numbers to any H2 heading that already carries a numeric prefix (`^\d+\.`). Preamble H2s like `Customer:` and `Date:` are never renumbered.

**Rule:** New sections inserted via `add` ops use a temporary `0.` prefix. The renumbering pass always runs last — never skip it.

---

### Token Efficiency Rules for Document Editing

The `edit_procedure_doc` flow is designed to avoid sending the full document to Claude on every call. Maintain these properties when modifying the edit pipeline:

| Operation | What goes to Claude | What Claude returns |
|---|---|---|
| Planning | Heading outline only (~200 chars) | JSON ops list (~200 chars) |
| Remove | Nothing — pure Python | Nothing |
| Modify | Single section body (~2k chars) | Rewritten section body |
| Add | Day heading + instruction | New section body |

**Never** send the full document text for an edit operation. The prior approach (send full doc, receive full doc) hit the 8192-token output limit for documents longer than ~400 lines, requiring continuation loops that still produced truncated results.

---

### Regenerating a Corrupted Document

If a procedure document shows signs of parser corruption (sections in wrong order, content inside code blocks that belongs outside, Day 2 missing):

1. Delete the corrupted files:
   ```bash
   rm output/<customer>/<customer>_procedure.md
   rm output/<customer>/<customer>_procedure.pdf
   ```
2. Run `build_procedure_doc` to generate a clean document from scratch.
3. Then run `edit_procedure_doc` for any customisations needed.

Do not try to manually repair a corrupted `.md` file and feed it back to `edit_procedure_doc` — the section structure will still be broken from the parser's perspective.

---

### PDF Rendering Rules

The PDF renderer (`fpdf2` + Helvetica) is latin-1 only. `_sanitize()` handles common substitutions automatically:

| Unicode | Replaced with |
|---|---|
| `—` (em dash) | `--` |
| `–` (en dash) | `-` |
| `'` `'` (curly quotes) | `'` |
| `"` `"` (curly double quotes) | `"` |
| `…` (ellipsis) | `...` |
| `•` (bullet) | `*` |
| `→` (arrow) | `->` |
| ` ` (non-breaking space) | ` ` |

Any character not in this map is replaced with `?`. The `.md` file always preserves the original Unicode — if full fidelity is needed, produce the PDF via Pandoc:
```bash
pandoc output/<customer>/<customer>_procedure.md -o <customer>_procedure.pdf
```

When writing `_SYSTEM_PROMPT_TEMPLATE` or `_SECTION_SYSTEM`, avoid instructing Claude to use Unicode bullet characters, arrows, or em-dashes in output — use ASCII equivalents so the PDF matches the Markdown.

---

## Part 3 — Style Reference Card

Quick lookup for consistent formatting decisions across both READMEs and procedure docs.

| Element | Rule |
|---|---|
| Headings | `#` title, `##` major section, `###` subsection — never skip levels |
| Code blocks | Always include language tag: `bash`, `json`, `ini`, `yaml`, `python` |
| Inline code | Backticks for filenames, flags, tool names, directory paths, env vars |
| Tables | Header row + separator row + data rows; separator uses ` | --- | ` (spaced) |
| Placeholders | `<SCREAMING_SNAKE>` — consistent throughout one document |
| Callouts | `>` for must-not-miss warnings only; never for informational text |
| Horizontal rules | `---` as top-level section separators only |
| File paths in text | Backtick-wrapped: `` `output/<customer>/` `` |
| Command examples | Start with `# comment` describing the action before the command |
| Empty lines | One blank line before and after every heading, code block, and table |
| Numbered lists | Use `1. 2. 3.` not `1) 2) 3)` |
| Procedure steps | One atomic action per step — never combine two actions in one step |
| Verification | Every verification item must state the command AND the expected output |
