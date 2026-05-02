# SKILL: generate_tracker

## Trigger
Use this skill when generating any customer engagement tracker Excel workbook via the
`generate_tracker` MCP tool. Applies to any Platform9 PCD customer — not customer-specific.

---

## Purpose
Produce a `.xlsx` workbook used during active Platform9 PCD engagements to track open
queries, integration issues, and filed engineering bugs from weekly sync calls (issues
tracker), or to track SOW deliverables and milestones (SOW tracker).

---

## tracker_type: `"issues"`

### Input
Raw text (weekly sync notes, pasted from a doc) OR a JSON array of issue objects.

**JSON issue object schema:**
```json
{
  "summary":   "One-line description of the issue or query",
  "status":    "Done | Not_started | In-discussion | Engineering | Blocked",
  "priority":  "high | medium | low",
  "product":   "PCD-V | VJAILBREAK | MAAS | OTHER",
  "ownership": "Platform9 | PF9/Customer | Customer | Engineering",
  "comment":   "Current status notes, workaround, or resolution detail",
  "jira_link": "https://platform9.atlassian.net/browse/TICKET-123 or null"
}
```

**When input is raw text**, use Claude to extract issues with these rules:
- Items with a Jira link (`platform9.atlassian.net`) AND product context → `Bug_reported` sheet
- Items with ownership context → `Issue_tracker` sheet
- **Status inference:** resolved/fixed/complete → `Done`; pending/TBD/not started → `Not_started`; discussing/in process/awaiting → `In-discussion`; Jira filed → `Engineering`
- **Priority inference from signal words:** blocking/critical/production/security → `high`; integration/performance/important → `medium`; doc/RFE/cosmetic → `low`
- **Product inference from Jira prefix:** `PCD-*` → `PCD-V`; `VJAILB-*` → `VJAILBREAK`; `MAAS-*` → `MAAS`
- **Ownership default:** `Platform9` unless text explicitly names the customer team

### Workbook structure (4 sheets)

**Sheet 1: `Summary`**
- Header block: Customer, Product Version, Prepared By, Last Updated
- Count table: Issues by Status (Done / In-Discussion / Not Started / Total)
- Count table: Issues by Priority (High / Medium / Low per status)
- Count table: Bugs by Product (PCD-V / VJAILBREAK split by priority)
- Open Action Items list (status ≠ Done, sorted High → Medium → Low)

**Sheet 2: `Issue_tracker`**

| Column | Width | Notes |
|---|---|---|
| ID (I-001…) | 8 | Auto-assigned |
| Summary | 55 | Wrap text |
| Status | 15 | Colour-coded (see below) |
| Priority | 12 | Colour-coded (see below) |
| Product | 14 | |
| Version | 18 | |
| Ownership | 15 | |
| Comment / Bug Link | 55 | Hyperlink if URL |
| Target Date | 14 | |
| Resolution Notes | 45 | |

**Sheet 3: `Bug_reported`**

| Column | Width | Notes |
|---|---|---|
| ID (B-001…) | 8 | Auto-assigned |
| Summary | 55 | `[RFE]` prefix in italic if feature request |
| Status | 15 | Always `Engineering` for filed bugs |
| Priority | 12 | Colour-coded |
| Product | 14 | |
| Version | 18 | |
| Jira Link | 30 | Clickable hyperlink |
| Target Date | 14 | |
| Resolution Notes | 45 | |

**Sheet 4: `Open Actions`**
All issues/bugs where status ≠ `Done` and ≠ `Engineering`.
Columns: Sheet (Issue/Bug) + same as Issue_tracker.
Sort: Priority desc (High → Medium → Low), then Status.

### Status colour coding

| Status | Cell Fill | Font colour |
|---|---|---|
| `Done` | `#C6EFCE` | `#276221` |
| `Not_started` | `#FFEB9C` | `#9C5700` |
| `In-discussion` | `#DDEBF7` | `#1F4E79` |
| `Engineering` | `#FCE4D6` | `#833C00` |
| `Blocked` | `#FFCCCC` | `#9C0006` |

### Priority colour coding

| Priority | Cell Fill | Font |
|---|---|---|
| `high` | `#FF0000` | White bold |
| `medium` | `#FF9900` | White bold |
| `low` | `#92D050` | Dark |

Normalise all priority values to title-case on write.

### ID assignment
- Issues: `I-{seq:03d}` from `I-001`
- Bugs: `B-{seq:03d}` from `B-001`
- Stable across regenerations if existing IDs provided

---

## tracker_type: `"sow"`

Input: `SowDocument` JSON string (output of `parse_sow` tool, or hand-constructed).

Workbook structure (3 sheets):
- **Summary**: customer metadata, delivery phases, DCs, VM/hypervisor counts, integrations
- **Per scope section** (one sheet each, named `{id} {title[:25]}`): deliverables table
  Columns: ID, Title, Type, Owner, Est. Hours, Target Date (blank), Status (Not Started), Notes
  Activities panel below the deliverables table
- **All Deliverables**: master list across all sections with auto-filter

---

## tracker_type: `"combined"`

Produces a single workbook containing all sheets from both `"issues"` and `"sow"` types.
Tab order: Summary → Issue_tracker → Bug_reported → Open Actions → [SOW section sheets] → All Deliverables

---

## Output file naming

`<customer>_<tracker_type>_tracker_<YYYYMMDD>.xlsx`

Examples:
- `Acme_issues_tracker_20260502.xlsx`
- `Acme_sow_tracker_20260502.xlsx`

Written via `OutputWriter` to `output/<customer>/<timestamp>/`.

---

## Branding

- Sheet tab colours: Summary=`#1F4E79`, Issue_tracker=`#2E75B6`, Bug_reported=`#ED7D31`, Open Actions=`#70AD47`
- Header row: fill `#1F4E79`, white bold Calibri 11pt, height 28px
- Alternating rows: odd=`#DEEAF1`, even=`#FFFFFF`
- All formatting defined in `sow_mcp/templates/excel_styles.py` — no inline styles
