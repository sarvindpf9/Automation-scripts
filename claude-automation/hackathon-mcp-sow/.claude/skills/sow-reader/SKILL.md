# SKILL: parse_sow

## Trigger
Use this skill when the `parse_sow` MCP tool is called with a SOW PDF, or when a user
uploads a SOW document to generate procedure docs, engagement trackers, or scope summaries.

---

## Purpose
Extract only the following sections from a Platform9 PCD SOW PDF and structure them for
downstream document generation. Ignore all other sections (commercial terms, legal boilerplate,
payment schedules, signatures).

**Target sections** (extracted in this order):

| # | Section | Purpose |
|---|---|---|
| 1 | Objectives | Engagement goals; frames Day 0 in procedure doc |
| 2 | Scope of Work | Activity list per phase; drives Day 1 steps |
| 3 | Deliverables | Named artifacts; populates tracker rows |
| 4 | Assumptions | Pre-conditions; feeds Day 0 prerequisites checklist |
| 5 | Acceptance Criteria | Sign-off conditions; feeds Day 2 validation steps |
| 6 | Out of Scope | Exclusions; scoping notes in Day 0 |
| 7 | VM Migrations | Migration scope; feeds Day 2 migration section |

Sections absent from the SOW are omitted silently — do not invent placeholder content.

---

## Section Matching Rules

Match headings **case-insensitively**. Accept common variants:

| Target | Accept also |
|---|---|
| Objectives | Project Objectives, Engagement Objectives, Goals |
| Scope of Work | Scope, Project Scope, Statement of Work, Services |
| Deliverables | Key Deliverables, Project Deliverables, Deliverable List |
| Assumptions | Key Assumptions, Assumptions and Dependencies |
| Acceptance Criteria | Acceptance, Definition of Done, Sign-off Criteria |
| Out of Scope | Exclusions, Not in Scope, Excluded Services |
| VM Migrations | Workload Migration, VM Migration Scope, Migration Services |

Extract the full section text including all sub-headings and bullet points beneath the heading.
Stop at the next top-level heading or horizontal rule.

---

## Extraction Schema

### Deliverables
Each deliverable must capture:

```json
{
  "id":              "D-4.1-1",
  "section_id":      "4.1",
  "title":           "Short deliverable title",
  "type":            "report | configuration | runbook | training | document",
  "owner":           "Platform9 | Customer | Joint",
  "estimated_hours": 184
}
```

- `id`: use the SOW's own numbering if present; otherwise auto-assign `D-{section}-{seq}`
- `estimated_hours`: `null` if not stated — never infer or estimate
- `type`: infer from title keywords: "report/assessment/validation" → `report`; "install/configure/design" → `configuration`; "runbook/procedure" → `runbook`; "training/knowledge transfer" → `training`; default → `document`

### VM Migrations
If a VM migration section is present:

```json
{
  "vm_count":        500,
  "source_platform": "VMware vSphere",
  "tool":            "vJailbreak",
  "target_project":  "<PROJECT_NAME>",
  "timeline":        "Phase 3 — 8 weeks"
}
```

All fields `null` if not stated — do not guess.

### Assumptions
Flat string array — one item per bullet or numbered point:

```json
["Customer provides IPMI access to all hosts before Day 1",
 "All hosts meet minimum hardware spec per PCD BOM"]
```

### Acceptance Criteria
Flat string array. If criteria are linked to a specific deliverable ID in the SOW, capture the mapping:

```json
[
  {"deliverable_id": "D-4.1-2", "criteria": "PCD environment passes pre-production validation suite"},
  {"deliverable_id": null,       "criteria": "All integrations validated by customer ops team"}
]
```

### Out of Scope
Flat string array — one exclusion per item.

---

## Output: SowDocument field mapping

| SowDocument field | Source section |
|---|---|
| `customer` | Cover page / title block |
| `project_title` | Title block |
| `objectives` | Objectives |
| `phases` | Scope of Work — top-level sub-headings |
| `scope_sections[].activities` | Scope of Work — bullet lists per sub-heading |
| `scope_sections[].deliverables` | Deliverables (matched to parent section by ID prefix) |
| `assumptions` | Assumptions |
| `acceptance_criteria` | Acceptance Criteria |
| `out_of_scope` | Out of Scope |
| `vm_migrations` | VM Migrations |

Fields absent from the SOW → `null` or `[]`. Never invent values; use `<PLACEHOLDER>` only
when the field is structurally required by a downstream tool.

---

## Context cap behaviour

If the SOW PDF exceeds the 6 000-character per-document extraction limit, prioritise sections
in this order — truncate lower-priority sections before dropping higher-priority ones:

1. Scope of Work
2. Deliverables
3. Objectives
4. Assumptions
5. Acceptance Criteria
6. Out of Scope
7. VM Migrations

Log a warning for any truncated or skipped section.

---

## Downstream tools

### → `generate_tracker` (tracker_type="sow")
Passes the full `SowDocument` JSON. The tracker uses:
- `scope_sections` + `deliverables` → one Excel sheet per scope section
- `phases`, `datacenters`, `vm_migrations` → Summary sheet metadata

### → `build_procedure_doc`
The procedure generator uses:
- `objectives` → framing paragraph in Day 0 Infrastructure Assessment
- `scope_sections` + `deliverables` → Day 1 activity steps and checklist items
- `assumptions` → Day 0 Prerequisites Checklist
- `out_of_scope` → scoping boundary notes in Day 0
- `vm_migrations` → Day 2 VM Migration section (tool, count, timeline)
- `acceptance_criteria` → Day 2 Operational Readiness Validation steps
