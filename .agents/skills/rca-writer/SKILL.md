---
name: rca-writer
description: "Use this skill to draft a Platform9 Root Cause Analysis document. Triggers: 'write rca', 'draft rca', 'create rca', 'write root cause analysis', 'prepare rca for <customer>'. Gathers incident facts from the user or from pasted logs/notes, then produces a complete RCA in Platform9 format."
---

# RCA Writer Skill

## Behaviour

- If the user pastes raw incident notes, log excerpts, or a timeline: extract facts from those and populate the template. Do not invent values not present in the source material.
- If the user provides only a brief description: ask the single most blocking question before proceeding (usually: what was the primary trigger?).
- All env-specific values that are unknown must appear as `<PLACEHOLDER>` — never invent plausible-sounding defaults.
- Evidence status must be stated honestly. If a section lacks confirmed log evidence, say "Pending" or "Unconfirmed."
- Timestamps: always record both the customer local timezone and UTC. Convert relative references ("the next morning") to absolute timestamps where possible.
- All corrective actions require an Owner column. If ownership is unclear, mark as `<TBD>`.

## Intake Questions (ask only the blocking ones, one at a time)

Before drafting, confirm the following. Skip any that are already answered in the user's input:

1. Customer name and environment FQDN
2. Ticket / case number
3. Incident date range and primary trigger event (what broke, when)
4. PCD/platform version affected
5. Prepared by (name + email), Reviewed by (name + email) if known, and Edited by (name, title, email) — do not default to any specific person; use only what the user provides

## Output Format

Codex produces output in two modes:

- **Mode 1 — Markdown** (`.md`): always produced; printed to the conversation or written to `<customer-slug>_rca_<YYYYMMDD>.md`.
- **Mode 2 — Google Apps Script** (`.gs`): produced when the user explicitly requests a Google Doc version. The script, when run in a Google Workspace Apps Script project, creates a fully styled document matching the Platform9 RCA visual theme.

If neither format nor output path is specified, ask before generating.

---

### Mode 1 — Markdown

Produce the full RCA as a single Markdown document following the structure below. Every section heading, table structure, and ordering must match exactly.

---

````markdown
# Root Cause Analysis for <CUSTOMER>

**<INCIDENT SHORT DESCRIPTION>**
**<DATE RANGE>**
**#<TICKET_NUMBER>**

**Date:** <RCA publication date>
**Prepared By:** <Name> (<email@platform9.com>)
**Reviewed By:** <Name> (<email>) — leave blank if not yet reviewed
**Edited By:** <Name>, <Title> (<email>) — populate only from user-provided input; never default to a specific person

*Platform9 Confidential*

---

## 1. Executive Summary

<2–4 paragraph narrative. Cover in order:>
<  1. What broke, when, and how many workloads were affected.>
<  2. The primary trigger (single root cause sentence, bold the trigger name).>
<  3. Pre-existing conditions that amplified severity — each as a bold bullet.>
<  4. What this document covers (sections referenced by number).>
<  5. Total corrective action count and how many are immediately actionable.>

### EVIDENCE STATUS

> <State which log sources confirm the root cause, which pre-existing conditions are confirmed
> and from which hosts/logs, and which items remain unconfirmed or pending external input.>

---

## 2. Incident Summary

| Field | Value |
|---|---|
| **Customer** | <Customer Name> |
| **Environment** | <env-fqdn.app.pcd.platform9.com> |
| **PCD Version** | <vYYYY.MM-BUILD> |
| **Incident Trigger** | <Date, time (local + UTC) — one-line description of triggering event> |
| **Cascade Event** | <Date, time (local + UTC) — the moment impact became widespread> |
| **Service Restored** | <Date, time (local + UTC) — first workload online; full recovery time if different> |
| **Total Duration** | <Approx. hours from cascade to full recovery> |
| **Affected Hosts** | <Comma-separated hostnames> |
| **Workloads Impacted** | <Count and state — e.g., "52 VMs in ERROR/SHUTOFF"> |
| **Impact** | <Description of customer-facing services lost> |
| **Recovery Method** | <One-line description of how workloads were restored> |
| **Storage / Infra** | <Storage cluster, nodes, driver version, or equivalent infra detail> |
| **SVM / Volume / Backend** | <SVM name / volume name, or equivalent backend identifier> |
| **HA Segment / Zone** | <HA segment name and status at incident time> |
| **Severity** | P<1|2|3> / <Critical|High|Medium> |

---

## 3. Root Cause Analysis

<1–2 sentence framing: single trigger + pre-existing amplifiers + structure of this section.>

### 3.1 Primary Trigger: <Trigger Name>

<Describe the root cause storage/network/software event. Cite the specific log event, API call,
or metric that confirms it. Use a code block for the key log line(s).>

#### 3.1.1 Advance Warnings

<Were there alerts before the trigger? List them with timestamps, severity, and whether they
were actioned. If ONTAP or equivalent suppressed repeat alerts, note the suppression behaviour.>

#### 3.1.2 Precipitating Event

<The specific operation that consumed the last headroom / triggered the fault. Include the
ASUP / log evidence in a code block. Note whether it was a platform-initiated or customer-initiated
operation.>

```
<key log line confirming precipitating event>
```

#### 3.1.3 Cascade Event

<The moment the fault became widespread — LUNs offline, network partition, process crash, etc.
Cite the count of affected resources and the exact timestamp. If multiple error types fired
simultaneously, list them as bullets.>

- **<event-type> (severity: <ALERT|ERROR>):** "<log message>"
- **<N> write/path failures:** description
- **<N> resource-offline events:** description

#### 3.1.4 Recovery of Primary Resource

<When did the storage/network/service return to OK state, and what is the confirmed or
suspected mechanism? Note any gap between the ASUP/log evidence and verbal statements
made during the incident sync call — track the discrepancy in Section 9.>

> **FINDING: <FINDING TITLE>**
> <If evidence is missing or contradictory for this sub-section, call it out in a blockquote.
> State what is confirmed, what is inferred, and what requires external verification.>

### 3.2 Contributing Pre-Conditions

<Explain that the trigger alone would not have produced the observed duration/blast-radius.
State the number of pre-existing conditions and which component/host each affects.>

#### 3.2.1 <Pre-Condition Title — e.g., Stale Process on Host X>

<Describe the pre-existing state: what it was, when it originated, and why it was never cleaned up.
Include a code block for the process listing or log line that confirms its age/state.>

```
<process listing, log line, or config snippet confirming the pre-condition>
```

<Explain the specific way this pre-condition worsened the incident outcome.>

#### 3.2.2 <Pre-Condition Title — e.g., Service Already Degraded on Host X>

<Same structure as 3.2.1.>

```
<confirming log line>
```

#### 3.2.3 <Pre-Condition Title — e.g., HA Segment Blocked>

<Same structure. If segment/zone-level, explain the scope: which hosts were affected and
how long the condition had persisted before the incident.>

### 3.3 Stage 1: <First Propagation Stage Title>

<How did the primary resource failure propagate to the compute/network/application layer?
Include the specific configuration or behaviour that enabled propagation (e.g., multipath policy,
retry config, timeout value). Use a code block for the relevant config snippet.>

```
<config snippet that enabled propagation>
```

<Note any secondary observations (e.g., missing hardware handler, stale igroup) that indicate
prior incomplete cleanup operations.>

### 3.4 Stage 2: <Second Propagation Stage Title>

<How did Stage 1 propagate to the next layer (e.g., process deadlock, service hang)?
Cite the specific kernel/application behaviour that prevented signals or recovery.
List per-host evidence as bullets.>

**Evidence from the affected hosts:**

- **<HOST1>:** <what failed and what log/command confirms it>
- **<HOST2>:** <what failed>

```
<log line confirming Stage 2 failure on the most illustrative host>
```

### 3.5 Stage 3: <Third Propagation Stage Title>

<How did Stage 2 cause the customer-visible impact? Cover state divergence between
management plane and hypervisor, service crash loops, and why automated recovery
did not trigger. Use bullet points for the cascading effects.>

- **<Effect 1>:** description
- **<Effect 2>:** description
- **<Effect 3 — automated recovery failure>:** description

### 3.6 Why <Layer X> Did Not Recover When <Layer Y> Recovered

<Enumerate the specific mechanisms — numbered or bulleted — that prevented self-healing
once the primary resource returned to OK state. Each mechanism should be self-contained:
what blocked recovery, the technical reason, and the evidence. This section is critical for
customer understanding.>

- **<Mechanism 1>:** <technical explanation with evidence>
- **<Mechanism 2>:** <technical explanation>
- **<Mechanism 3>:** <technical explanation>
- **<Mechanism 4>:** <technical explanation>

<Conclude with what manual actions were required, why they were required, and why
in-place recovery was or was not possible.>

---

## 4. Recovery Complications

<Brief intro: factors that compounded difficulty and extended duration.>

### 4.1 <Complication 1 — e.g., Automated Evacuation Blocked>

<What blocked automated recovery? Explain the safety algorithm's correct behaviour and
why it still prevented recovery in this scenario.>

### 4.2 <Complication 2 — e.g., Resource Mapping Drift>

<Describe the stale/drifted state that accumulated during manual recovery attempts.
Include the specific host and resource identifiers where the drift is confirmed.>

### 4.3 <Complication 3 — e.g., Capacity or Resource Constraint>

<Describe any capacity bottleneck that constrained the recovery options.>

### 4.4 Recovery Procedure Used

<Describe the procedure actually used step-by-step. Number the steps. Note duration per
unit (e.g., per VM) and total recovery time. If faster alternatives were identified
post-incident, note them here.>

1. <Step 1>
2. <Step 2>
3. <Step 3>
...

<Total recovery time: from first workload restored to last.>

**Alternative recovery paths identified post-incident:**

1. <Faster path 1 — describe the approach and why it would have been faster>
2. <Faster path 2 if applicable>

---

## 5. Timeline of Events

All times in <LOCAL TIMEZONE> (abbreviated). UTC in parentheses where derived from logs.
<TIMEZONE> = UTC <+/-OFFSET>.

| Time | Event |
|---|---|
| <DATE, HH:MM TZ> | <Description. Reference section number in parentheses if detailed elsewhere.> |
| <DATE, HH:MM TZ> | <Description> |
| ... | ... |

---

## 6. Five Whys Analysis

| # | Why | Finding |
|---|---|---|
| 1 | Why did <top-level symptom>? | <Finding — describe the mechanism, not just the cause> |
| 2 | Why did <cause from row 1>? | <Finding> |
| 3 | Why did <cause from row 2>? | <Finding> |
| 4 | Why was <condition from row 3> never cleaned up / detected? | <Finding — include the process/policy gap> |
| 5 | Why did <mitigation mechanism> not recover the situation? | <Finding — cover both automated and manual mitigation failures> |

---

## 7. Causal Chain Summary

Each step is a direct consequence of the preceding step.

| # | Event |
|---|---|
| 1 | <Triggering action — what the platform or operator did that initiated the chain> |
| 2 | <Primary resource exhaustion / failure event with timestamp> |
| 3 | <Propagation to dependent resources> |
| 4 | <Process/service failure caused by propagation> |
| 5 | <Management plane impact> |
| 6 | <Customer-visible impact — VM/service state> |
| 7 | <Automated recovery mechanism and why it did not trigger> |
| 8 | <Manual recovery attempt and why it also failed> |
| 9 | <Primary resource recovery and timestamp> |
| 10 | <State divergence that persisted after primary resource recovered> |
| 11 | <Manual intervention required — per host, what was done> |
| 12 | <Final recovery method and total time> |

---

## 8. Corrective Actions and Recommendations

### 8.1 Immediate Actions

| # | Action | Owner |
|---|---|---|
| 1 | <Action — specific, actionable, includes what to verify or configure> | <Team / Role> |
| 2 | <Action> | <Team / Role> |
| ... | ... | ... |

### 8.2 Short-Term Actions

| # | Action | Owner |
|---|---|---|
| <N> | <Action> | <Team / Role> |
| ... | ... | ... |

### 8.3 Long-Term Recommendations

| # | Action | Owner |
|---|---|---|
| <N> | <Action> | <Team / Role> |
| ... | ... | ... |

### 8.4 Reference Commands and Configurations

<Include only configurations or commands that are directly relevant to the corrective actions
above. Use separate sub-headings per topic. Each block must have a language tag.>

#### <Config Topic 1 — e.g., Recommended multipath configuration>

```
<config block>
```

#### <Config Topic 2 — e.g., Recommended iscsid timing parameters>

```ini
<config block>
```

#### <Procedure — e.g., Snapshot-based VM recovery>

```bash
# Step 1: <description>
<command>

# Step 2: <description>
<command>
```

---

## 9. Open Items Pending Resolution

| # | Open Item | Status |
|---|---|---|
| A | <Unresolved question — be specific about what needs to be confirmed and by whom> | Pending <Team> verification |
| B | <Open item> | Pending <Team> action |
| ... | ... | ... |

---

**Platform9 — <Edited By Name>, <Edited By Title>**
<Sign-off date>
*Platform9 Confidential*
````

---

### Mode 2 — Google Apps Script

#### Platform9 RCA Visual Theme Constants

These hex values are extracted from the Platform9 RCA reference document. Use them verbatim in every generated `.gs` file — do not substitute or approximate.

```javascript
// Platform9 RCA — visual theme constants (extracted from reference PDF)
const THEME = {
  BLUE:           '#0089C7',  // page headers, section headings, ticket number
  NAVY:           '#0E1135',  // cover title, table header row background
  BODY:           '#3C3C57',  // body paragraph text
  TABLE_HDR_BG:   '#0E1135',  // multi-column table header row fill
  TABLE_HDR_FG:   '#FFFFFF',  // white text on table header rows
  TABLE_ALT_ROW:  '#EDF5FA',  // alternating data row tint
  CALLOUT_BG:     '#F9F9F9',  // EVIDENCE STATUS / FINDING box fill
  CALLOUT_BORDER: '#DDDDDD',  // callout and table border
  CODE_BG:        '#F4F4F6',  // code block / log excerpt fill
};

const PT = {
  COVER_TITLE:    28,
  COVER_SUBTITLE: 14,
  H1:             16,   // "1. Executive Summary"
  H2:             13,   // "3.1 Primary Trigger"
  H3:             11,   // "3.1.1 Advance Warnings"
  BODY:           10,
  CODE:            9,
  FOOTER:          8,
};
```

#### GAS Script Structure

The `.gs` file must open with the usage comment block below, then implement `createRCA()` as the entry point plus one private function per section. All content is embedded as string literals — the script must run standalone with no external data dependencies.

```javascript
/*
 * Platform9 RCA — Google Doc generator
 * How to use:
 *   1. Open script.google.com → New project.
 *   2. Paste this entire file, replacing the default content.
 *   3. Click Run → createRCA and authorize Docs access.
 *   4. The new document URL is printed to the Execution log.
 */

function createRCA() {
  const doc  = DocumentApp.create('<FULL DOCUMENT TITLE>');
  const body = doc.getBody();
  body.clear();
  _setBodyDefaults(body);
  _addPageHeader(doc);
  _addPageFooter(doc);

  _buildCoverPage(body);
  body.appendPageBreak();

  _buildExecutiveSummary(body);
  _buildIncidentSummary(body);
  _buildRootCauseAnalysis(body);
  _buildRecoveryComplications(body);
  _buildTimeline(body);
  _buildFiveWhys(body);
  _buildCausalChain(body);
  _buildCorrectiveActions(body);
  _buildOpenItems(body);

  doc.saveAndClose();
  Logger.log('Document created: ' + doc.getUrl());
}
```

#### Element Helper Functions

Every generated `.gs` file must include these helpers. Populate the section-builder functions (`_buildExecutiveSummary`, etc.) using only these helpers — never inline `appendParagraph` calls with ad-hoc formatting.

**Body defaults:**
```javascript
function _setBodyDefaults(body) {
  body.setMarginTop(72).setMarginBottom(72)
      .setMarginLeft(72).setMarginRight(72);
  const s = {};
  s[DocumentApp.Attribute.FONT_FAMILY]      = 'Calibri';
  s[DocumentApp.Attribute.FONT_SIZE]        = PT.BODY;
  s[DocumentApp.Attribute.FOREGROUND_COLOR] = THEME.BODY;
  body.setAttributes(s);
}
```

**Running page header** ("Platform9  |  Root Cause Analysis" in THEME.BLUE, with a thin colored rule simulated by a 1-row table):
```javascript
function _addPageHeader(doc) {
  const hdr  = doc.addHeader();
  const para = hdr.appendParagraph('Platform9  |  Root Cause Analysis');
  para.editAsText().setFontSize(9).setBold(true)
      .setForegroundColor(THEME.BLUE).setFontFamily('Calibri');
  para.setSpacingAfter(0);
  const rule = hdr.appendTable([['']]);
  rule.setBorderWidth(0);
  rule.getRow(0).getCell(0)
      .setBackgroundColor(THEME.BLUE)
      .setPaddingTop(1).setPaddingBottom(1)
      .editAsText().setText('');
}
```

**Page footer** ("Platform9 Confidential", centered italic):
```javascript
function _addPageFooter(doc) {
  const ftr  = doc.addFooter();
  const para = ftr.appendParagraph('Platform9 Confidential');
  para.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  para.editAsText().setItalic(true).setFontSize(PT.FOOTER)
      .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
}
```

**H1 section heading** (e.g., "1. Executive Summary"):
```javascript
function _h1(body, text) {
  const p = body.appendParagraph(text);
  p.editAsText().setFontSize(PT.H1).setBold(true)
   .setForegroundColor(THEME.BLUE).setFontFamily('Calibri');
  p.setSpacingBefore(16).setSpacingAfter(6);
  return p;
}
```

**H2 sub-heading** (e.g., "3.1 Primary Trigger"):
```javascript
function _h2(body, text) {
  const p = body.appendParagraph(text);
  p.editAsText().setFontSize(PT.H2).setBold(true)
   .setForegroundColor(THEME.BLUE).setFontFamily('Calibri');
  p.setSpacingBefore(12).setSpacingAfter(4);
  return p;
}
```

**H3 sub-heading** (e.g., "3.1.1 Advance Warnings"):
```javascript
function _h3(body, text) {
  const p = body.appendParagraph(text);
  p.editAsText().setFontSize(PT.H3).setBold(true)
   .setForegroundColor(THEME.NAVY).setFontFamily('Calibri');
  p.setSpacingBefore(8).setSpacingAfter(2);
  return p;
}
```

**Body paragraph:**
```javascript
function _para(body, text) {
  const p = body.appendParagraph(text);
  p.editAsText().setFontSize(PT.BODY)
   .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
  p.setSpacingAfter(6);
  return p;
}
```

**Two-column field table** (Incident Summary — bold label left, value right, alternating rows, no header row):
```javascript
function _fieldTable(body, rows) {
  // rows: [['Label', 'Value'], ...]
  const tbl = body.appendTable();
  tbl.setBorderWidth(0.5).setBorderColor(THEME.CALLOUT_BORDER);
  rows.forEach(([label, value], i) => {
    const bg  = (i % 2 === 0) ? '#FFFFFF' : THEME.TABLE_ALT_ROW;
    const row = tbl.appendTableRow();

    const c0 = row.appendTableCell(label);
    c0.setBackgroundColor(bg)
      .setPaddingLeft(8).setPaddingRight(8)
      .setPaddingTop(5).setPaddingBottom(5);
    c0.editAsText().setBold(true).setFontSize(PT.BODY)
      .setForegroundColor(THEME.NAVY).setFontFamily('Calibri');

    const c1 = row.appendTableCell(value);
    c1.setBackgroundColor(bg)
      .setPaddingLeft(8).setPaddingRight(8)
      .setPaddingTop(5).setPaddingBottom(5);
    c1.editAsText().setFontSize(PT.BODY)
      .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
  });
  return tbl;
}
```

**Multi-column header table** (Five Whys, Causal Chain, Corrective Actions — dark navy header row, alternating data rows):
```javascript
function _headerTable(body, headers, rows) {
  // headers: ['#', 'Why', 'Finding']
  // rows:    [['1', 'Why...', 'Because...'], ...]
  const tbl = body.appendTable();
  tbl.setBorderWidth(0.5).setBorderColor(THEME.CALLOUT_BORDER);

  const hRow = tbl.appendTableRow();
  headers.forEach(h => {
    const cell = hRow.appendTableCell(h);
    cell.setBackgroundColor(THEME.TABLE_HDR_BG)
        .setPaddingLeft(8).setPaddingRight(8)
        .setPaddingTop(5).setPaddingBottom(5);
    cell.editAsText().setBold(true).setFontSize(PT.BODY)
        .setForegroundColor(THEME.TABLE_HDR_FG).setFontFamily('Calibri');
  });

  rows.forEach((cols, i) => {
    const bg  = (i % 2 === 0) ? '#FFFFFF' : THEME.TABLE_ALT_ROW;
    const row = tbl.appendTableRow();
    cols.forEach(text => {
      const cell = row.appendTableCell(text);
      cell.setBackgroundColor(bg)
          .setPaddingLeft(8).setPaddingRight(8)
          .setPaddingTop(5).setPaddingBottom(5);
      cell.editAsText().setFontSize(PT.BODY)
          .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
    });
  });
  return tbl;
}
```

**Code / log block** (monospace, light gray background, rendered as a single-cell table so background is visible):
```javascript
function _codeBlock(body, text) {
  const tbl  = body.appendTable([['']]);
  tbl.setBorderWidth(0.5).setBorderColor(THEME.CALLOUT_BORDER);
  const cell = tbl.getRow(0).getCell(0);
  cell.setBackgroundColor(THEME.CODE_BG)
      .setPaddingLeft(12).setPaddingRight(12)
      .setPaddingTop(8).setPaddingBottom(8);
  cell.getChild(0).asParagraph()
      .editAsText().setText(text)
      .setFontFamily('Courier New')
      .setFontSize(PT.CODE)
      .setForegroundColor(THEME.NAVY);
  return tbl;
}
```

**Callout box** (EVIDENCE STATUS, FINDING — near-white fill, gray border, bold THEME.BLUE title line):
```javascript
function _calloutBox(body, title, text) {
  const tbl  = body.appendTable([['']]);
  tbl.setBorderWidth(1).setBorderColor(THEME.CALLOUT_BORDER);
  const cell = tbl.getRow(0).getCell(0);
  cell.setBackgroundColor(THEME.CALLOUT_BG)
      .setPaddingLeft(14).setPaddingRight(14)
      .setPaddingTop(10).setPaddingBottom(10);
  cell.getChild(0).asParagraph()
      .editAsText().setText(title)
      .setFontFamily('Calibri').setFontSize(PT.BODY)
      .setBold(true).setForegroundColor(THEME.BLUE);
  cell.appendParagraph(text)
      .editAsText().setFontFamily('Calibri').setFontSize(PT.BODY)
      .setForegroundColor(THEME.BODY);
  return tbl;
}
```

#### Cover Page Layout

```javascript
function _buildCoverPage(body) {
  for (let i = 0; i < 6; i++) body.appendParagraph('');

  const title = body.appendParagraph('Root Cause Analysis for <CUSTOMER>');
  title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  title.editAsText().setFontSize(PT.COVER_TITLE).setBold(true)
       .setForegroundColor(THEME.NAVY).setFontFamily('Calibri');
  title.setSpacingAfter(8);

  const sub = body.appendParagraph('<INCIDENT SHORT DESCRIPTION>\n<DATE RANGE>');
  sub.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  sub.editAsText().setFontSize(PT.COVER_SUBTITLE).setBold(true)
     .setForegroundColor(THEME.NAVY).setFontFamily('Calibri');
  sub.setSpacingAfter(4);

  const ticket = body.appendParagraph('#<TICKET_NUMBER>');
  ticket.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  ticket.editAsText().setFontSize(PT.COVER_SUBTITLE).setBold(true)
        .setForegroundColor(THEME.BLUE).setFontFamily('Calibri');
  ticket.setSpacingAfter(32);

  [
    ['Date:',        '<RCA publication date>'],
    ['Prepared By:', '<Name> (<email>)'],
    ['Reviewed By:', '<Name> (<email>)'],
    ['Edited By:',   '<Name>, <Title> (<email>)'],
  ].forEach(([label, value]) => {
    const p = body.appendParagraph('');
    p.appendText(label).setBold(true).setFontSize(PT.BODY)
     .setForegroundColor(THEME.NAVY).setFontFamily('Calibri');
    p.appendText('\n' + value).setBold(false).setFontSize(PT.BODY)
     .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
    p.setSpacingAfter(6);
  });

  for (let i = 0; i < 8; i++) body.appendParagraph('');

  const conf = body.appendParagraph('Platform9 Confidential');
  conf.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  conf.editAsText().setItalic(true).setFontSize(PT.FOOTER)
      .setForegroundColor(THEME.BODY).setFontFamily('Calibri');
}
```

#### File Naming

| Output | Filename |
|---|---|
| Markdown | `<customer-slug>_rca_<YYYYMMDD>.md` |
| GAS script | `<customer-slug>_rca_<YYYYMMDD>.gs` |

If the user specifies an output path, write both files there. If no path is given, print the Markdown inline and the GAS script in a fenced `javascript` block labelled as a separate file.

---

## Section-by-Section Authoring Rules

### Executive Summary
- Open with the customer environment name, date, workload count, and host count.
- Name the primary trigger in one sentence; bold the trigger name.
- List pre-existing conditions as bold bullets below the trigger paragraph.
- Close with what this document covers and the total corrective action count.
- Never exceed 5 paragraphs.

### Incident Summary Table
- Every row must have a value or explicit "N/A." Never leave cells blank.
- Timestamps: local time first, UTC in parentheses.
- Severity follows `P<N> / <Label>` format: P1/Critical, P2/High, P3/Medium.

### Root Cause Analysis (Section 3)
- One trigger (3.1) + 1–4 pre-conditions (3.2.x) + 2–4 propagation stages (3.3–3.5).
- Section 3.6 is mandatory when the primary resource recovered but compute did not — this is the section customers read most carefully.
- Every claim of causation must reference a specific log line, command output, or ASUP event. If evidence is absent, say so explicitly.
- Use `> **FINDING:**` blockquotes for any finding that contradicts verbal statements made during the incident.

### Timeline
- Chronological. No gaps larger than the evidence supports.
- Reference the section where each event is analyzed in detail: `(Section 3.2.1)`.
- Use a single consistent timezone throughout; add UTC parenthetical for log-derived timestamps.

### Five Whys
- Exactly 5 rows. The fifth why must reach a process or policy gap, not a technical one.
- The "Finding" column describes the mechanism, not just the label. Minimum 2 sentences per row.

### Corrective Actions
- Group into Immediate (can be done now with existing access), Short-Term (requires planning or testing), Long-Term (architectural changes or new tooling).
- Every action must be specific enough that the owner can act on it without asking a clarifying question.
- Owner must be a team or named role, not a person's name (people change; teams don't).

### Open Items
- Letter-indexed (A, B, C...).
- Each item names what is unknown, what evidence or action would resolve it, and who is responsible.
- Remove items from this section and promote them to their corresponding section once resolved.

## Steps Codex Must Follow

1. Collect: incident facts from user input, pasted logs, or answers to intake questions.
2. Identify: trigger, pre-conditions, propagation stages, recovery complications, corrective actions. Flag anything that is inferred vs. log-confirmed.
3. Check: confirm output format(s) and path. If the user has not specified Markdown-only or both formats, ask. If an output path is provided, write files there; otherwise print to the conversation.
4. Draft: populate the Markdown template using only confirmed or explicitly inferred facts. Use `<PLACEHOLDER>` for any env-specific value not provided.
5. Review: verify that every Section 3 causal claim has a cited log line or ASUP event. Every corrective action has an owner. Every open item has a named responsible party.
6. Generate GAS (if requested): produce the `.gs` file using the helper functions from Mode 2. Every section-builder function must use only `_h1`, `_h2`, `_h3`, `_para`, `_fieldTable`, `_headerTable`, `_codeBlock`, and `_calloutBox` — no ad-hoc inline formatting. All RCA content from the Markdown draft is embedded as string literals in the corresponding builder function.
7. Deliver: write or print the final output(s). Print Markdown inline; print the GAS script in a fenced `javascript` block labelled clearly as a separate file. State which sections contain placeholders that require customer-side input before the RCA can be finalized.

## Constraints

- Do not invent IP addresses, hostnames, UUIDs, or log lines that were not provided.
- Do not pad the Five Whys beyond 5 rows.
- Do not add a "Lessons Learned" section — that content belongs in Section 8.3 Long-Term Recommendations.
- Do not add a "Customer Statement" section — customer-provided information is cited inline where relevant.
- Do not soften ownership language — if Platform9 engineering owns a corrective action, say so.
- The document is confidential by default. Include "Platform9 Confidential" on the cover and footer of each section.
