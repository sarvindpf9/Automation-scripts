"""Generate a Day0/Day1/Day2 deployment procedure document using Claude."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import anthropic
from fpdf import FPDF

from ..output_writer import OutputWriter

log = logging.getLogger(__name__)

_UNICODE_REPLACEMENTS = str.maketrans(
    {
        "—": "--",   # em dash
        "–": "-",    # en dash
        "'": "'",    # left single quote
        "'": "'",    # right single quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "…": "...",  # ellipsis
        "•": "*",    # bullet
        "→": "->",   # right arrow
        " ": " ",  # non-breaking space
        "’": "'",  # right apostrophe
    }
)


def _sanitize(text: str) -> str:
    """Replace non-latin-1 characters that core PDF fonts cannot encode."""
    return text.translate(_UNICODE_REPLACEMENTS).encode("latin-1", errors="replace").decode("latin-1")


# Maximum characters extracted per source document
_MAX_CHARS_PER_DOC = 6000
# Maximum total combined context characters sent to Claude
_MAX_TOTAL_CHARS = 40_000

_SYSTEM_PROMPT_TEMPLATE = """\
You are a Platform9 Solutions Architect producing a deployment procedure document for a customer engagement.

Using the reference documentation provided, produce a comprehensive Day 0 / Day 1 / Day 2 procedure document.

Structure the output as Markdown with exactly this top-level structure:

# Platform9 Private Cloud Director — Deployment Procedure
## Customer: {customer_name}
## Prepared by: Platform9 Strategic Customer Engineering
## Date: {today}

---

# Day 0 — Pre-Deployment Planning

## 1. Infrastructure Assessment
### Overview
### Prerequisites Checklist
### Steps

## 2. Network & Storage Planning
### Overview
### Prerequisites Checklist
### Steps

## 3. Integration Planning
### Overview
### Prerequisites Checklist
### Steps

---

# Day 1 — Deployment & Configuration

## 1. PCD Installation (Canary)
### Prerequisites
### Procedure
### Verification
### Rollback

## 2. MaaS Setup & Hypervisor Onboarding
### Prerequisites
### Procedure
### Verification
### Rollback

## 3. Storage Integration
### Prerequisites
### Procedure
### Verification
### Rollback

## 4. Network Integration (IPAM/DHCP/DNS)
### Prerequisites
### Procedure
### Verification
### Rollback

## 5. Monitoring Integration
### Prerequisites
### Procedure
### Verification
### Rollback

## 6. SSO / Identity Integration
### Prerequisites
### Procedure
### Verification
### Rollback

---

# Day 2 — Operations

## 1. VM Migration (Pilot)
### Overview
### Prerequisites
### Procedure
### Verification

## 2. Full-Scale VM Migration
### Overview
### Prerequisites
### Procedure
### Verification

## 3. Monitoring & Alerting Configuration
### Overview
### Procedure
### Verification

## 4. Backup Configuration
### Overview
### Procedure
### Verification

## 5. Operational Runbooks
### Overview
### Runbook: Hypervisor Maintenance
### Runbook: VM Recovery
### Runbook: Storage Expansion

## 6. Knowledge Transfer & Handover
### Overview
### Topics Covered
### Acceptance Criteria

---

Rules:
- Use <PLACEHOLDER> for any environment-specific value not found in the provided docs.
- Each Procedure section must have numbered steps. Each step is one atomic action.
- Verification sections must list specific commands or checks with expected output.
- Rollback sections must be present in Day 1 sections. If true rollback is not possible, state that and describe the impact.
- Draw content from the provided documentation. Do not invent technical details not supported by the docs.
"""


def generate_procedure_doc(
    customer_name: str,
    docs: list[dict],
    output_writer: OutputWriter,
    reference_urls: list[str] | None = None,
) -> tuple[Path, Path]:
    """
    Synthesize a Day0/Day1/Day2 procedure document from reference docs.

    Args:
        customer_name:   Customer name for headers and filenames.
        docs:            List of {"filename", "path", "text"} dicts from docs_reader.
        output_writer:   OutputWriter instance for file I/O.
        reference_urls:  Optional list of reference URLs (appended as footnotes only).

    Returns:
        Tuple of (markdown_path, pdf_path).
    """
    today = date.today().isoformat()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        customer_name=customer_name,
        today=today,
    )

    # Build combined context block — truncate per doc then cap total
    context_parts: list[str] = []
    total_chars = 0
    for doc in docs:
        chunk = doc["text"][:_MAX_CHARS_PER_DOC]
        if total_chars + len(chunk) > _MAX_TOTAL_CHARS:
            remaining = _MAX_TOTAL_CHARS - total_chars
            if remaining <= 0:
                log.warning("Total context cap reached — skipping %s", doc["filename"])
                continue
            chunk = chunk[:remaining]
            log.info("Truncating %s to fit total cap", doc["filename"])
        context_parts.append(f"--- Document: {doc['filename']} ---\n{chunk}")
        total_chars += len(chunk)

    combined_context = "\n\n".join(context_parts) if context_parts else "(No reference documents provided.)"
    log.info("Sending %d chars of doc context to Claude", total_chars)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": combined_context,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Using the above reference documentation, produce the complete "
                            f"Day 0 / Day 1 / Day 2 procedure document for {customer_name}."
                        ),
                    },
                ],
            }
        ],
    )

    log.debug(
        "Cache tokens — creation: %s  read: %s",
        getattr(response.usage, "cache_creation_input_tokens", "n/a"),
        getattr(response.usage, "cache_read_input_tokens", "n/a"),
    )

    md_text = response.content[0].text.strip()

    # Append reference URLs as a footnote section
    if reference_urls:
        url_lines = "\n".join(f"- {u}" for u in reference_urls)
        md_text += f"\n\n---\n\n## Reference URLs\n\n{url_lines}\n"

    safe_name = customer_name.replace(" ", "_")
    md_path = output_writer.write_text(f"{safe_name}_procedure.md", md_text)
    log.info("Markdown procedure written to %s", md_path)

    pdf_path = output_writer.path(f"{safe_name}_procedure.pdf")
    markdown_to_pdf(md_text, pdf_path, customer_name)
    log.info("PDF procedure written to %s", pdf_path)

    return md_path, pdf_path


# ---------------------------------------------------------------------------
# Section-aware document editing
# ---------------------------------------------------------------------------

@dataclass
class _DocSection:
    heading_line: str   # e.g. "## 2. MaaS Setup...\n"  (empty for preamble)
    heading_text: str   # e.g. "2. MaaS Setup..."        (empty for preamble)
    level: int          # 0=preamble, 1=H1, 2=H2
    body: str           # content below heading until next H1/H2


def _parse_sections(md: str) -> list[_DocSection]:
    """Split markdown at H1/H2 boundaries. H3+ stays in the body of its parent H2.

    Fenced code blocks (``` or ~~~) are tracked so that heading-like lines inside
    a fence are never treated as section boundaries — a common source of corruption
    when generated section bodies contain bash/ini comments starting with #/##.
    """
    sections: list[_DocSection] = []
    cur_heading_line = ""
    cur_heading_text = ""
    cur_level = 0
    cur_body: list[str] = []
    in_fence = False

    def _save() -> None:
        body_str = "".join(cur_body)
        if cur_heading_line or body_str.strip():
            sections.append(_DocSection(
                heading_line=cur_heading_line,
                heading_text=cur_heading_text,
                level=cur_level,
                body=body_str,
            ))

    for line in md.splitlines(keepends=True):
        # Toggle fence state on opening/closing fence markers (``` or ~~~, any length ≥ 3)
        if re.match(r"^(`{3,}|~{3,})", line):
            in_fence = not in_fence
            cur_body.append(line)
            continue

        # Only detect headings outside fenced blocks
        if not in_fence:
            m1 = re.match(r"^# (?!#)(.+)", line)
            m2 = re.match(r"^## (?!#)(.+)", line)
            if m1 or m2:
                _save()
                m = m1 or m2
                cur_heading_line = line
                cur_heading_text = m.group(1).strip()  # type: ignore[union-attr]
                cur_level = 1 if m1 else 2
                cur_body = []
                continue

        cur_body.append(line)

    _save()
    return sections


def _sections_to_md(sections: list[_DocSection]) -> str:
    return "".join(s.heading_line + s.body for s in sections)


def _heading_outline(sections: list[_DocSection]) -> str:
    """Compact heading tree used for the planning prompt."""
    lines: list[str] = []
    for s in sections:
        if s.level == 0:
            lines.append("[preamble]")
        elif s.level == 1:
            lines.append(f"# {s.heading_text}")
        else:
            lines.append(f"  ## {s.heading_text}")
    return "\n".join(lines)


def _find_h2(sections: list[_DocSection], heading: str) -> int:
    """Return index of H2 section matching heading (exact, then case-insensitive, then substring). -1 if none."""
    h_lower = heading.lower()
    for i, s in enumerate(sections):
        if s.level == 2 and s.heading_text == heading:
            return i
    for i, s in enumerate(sections):
        if s.level == 2 and s.heading_text.lower() == h_lower:
            return i
    # Substring: handles Claude omitting the numeric prefix (e.g. "MaaS Setup" vs "2. MaaS Setup")
    for i, s in enumerate(sections):
        if s.level == 2 and (h_lower in s.heading_text.lower() or s.heading_text.lower() in h_lower):
            return i
    return -1


def _find_h1(sections: list[_DocSection], heading: str) -> int:
    """Return index of H1 section matching heading (fuzzy). -1 if not found."""
    h_lower = heading.lower()
    for i, s in enumerate(sections):
        if s.level == 1 and s.heading_text.lower() == h_lower:
            return i
    for i, s in enumerate(sections):
        if s.level == 1 and h_lower in s.heading_text.lower():
            return i
    return -1


def _renumber_day_sections(sections: list[_DocSection]) -> list[_DocSection]:
    """Re-number H2 sections that carry a numeric prefix within each H1 block.

    Applies sequential 1, 2, 3... numbering only to sections whose heading_text
    already starts with a digit (e.g. "2. MaaS Setup"). Preamble H2s like
    "Customer: Acme" are left untouched.
    """
    result = list(sections)
    h1_indices = [i for i, s in enumerate(result) if s.level == 1]
    boundaries = [
        (h1_indices[k], h1_indices[k + 1] if k + 1 < len(h1_indices) else len(result))
        for k in range(len(h1_indices))
    ]
    for start, end in boundaries:
        counter = 1
        for i in range(start + 1, end):
            s = result[i]
            if s.level == 2 and re.match(r"^\d+\.", s.heading_text):
                bare = re.sub(r"^\d+\.\s+", "", s.heading_text)
                new_text = f"{counter}. {bare}"
                result[i] = replace(s, heading_text=new_text, heading_line=f"## {new_text}\n")
                counter += 1
    return result


_PLAN_SYSTEM = """\
You are analysing a Markdown procedure document to produce a JSON edit plan.

Return ONLY a JSON array. Each element must be one of:

Remove a H2 section:
{"op": "remove", "heading": "<H2 heading text exactly as shown in the outline>"}

Add a new H2 section:
{"op": "add", "day_heading": "<H1 heading text>", "after_heading": "<H2 heading text or null>", "title": "<new section title without a number prefix>", "instruction": "<one-line content summary>"}

Modify an existing H2 section:
{"op": "modify", "heading": "<H2 heading text exactly as shown in the outline>", "instruction": "<one-line description of the change>"}

Rules:
- Use heading text exactly as it appears in the outline (no leading # symbols).
- "day_heading" must be an H1 heading from the outline.
- "after_heading": H2 heading after which the new section is inserted; null to append at end of the day block.
- The "instruction" value MUST be a single-line string. Do NOT include literal newline characters,
  bullet points, or multi-line text inside any JSON string value. Summarise the intent in one sentence.
- Return only the JSON array — no preamble, no commentary, no code fences.
"""


def _repair_json(raw: str) -> str:
    """Escape bare newlines and control characters found inside JSON string values.

    Claude occasionally emits multi-line text inside a JSON string field which
    makes json.loads raise 'Unterminated string'. This walks the raw text as a
    character stream, tracking whether we are inside a string, and replaces any
    literal newline/carriage-return/tab with their JSON escape sequences.
    """
    out: list[str] = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            out.append(ch)
            escape_next = False
            continue
        if ch == "\\" and in_string:
            out.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string:
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
        out.append(ch)
    return "".join(out)


def _plan_edits(instructions: str, sections: list[_DocSection]) -> list[dict]:
    """Cheap planning call: sends the heading outline only, gets a JSON op list back."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_PLAN_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Document outline:\n{_heading_outline(sections)}\n\n"
                    f"Edit instructions: {instructions}"
                ),
            }
        ],
    )
    raw = response.content[0].text.strip()
    # Strip accidental markdown code fences
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    # Repair bare newlines inside JSON string values before parsing
    raw = _repair_json(raw)
    return json.loads(raw)


_SECTION_SYSTEM = """\
You are a Platform9 Solutions Architect writing one section of a deployment procedure document.

Output ONLY the section body — do NOT include the H2 heading line itself.

Structure:
### Overview  (for Day 0 sections)   OR   ### Prerequisites  (for Day 1 / Day 2 sections)
<1-2 sentence purpose statement>

### Prerequisites
- Pre-conditions (bullet list)

### Procedure
1. Numbered atomic steps — one action per step

### Verification
- Specific commands and their expected output

### Rollback   <- REQUIRED for Day 1 sections; omit for Day 0 and Day 2
- Steps to reverse the procedure; if not reversible state that explicitly and describe impact

Rules:
- Use <PLACEHOLDER> for any environment-specific value not provided in the instructions.
- Output Markdown only — no surrounding prose, no horizontal rules at start/end.
"""


def _write_section(title: str, day_heading: str, instruction: str) -> str:
    """Generate body content for a brand-new section."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_SECTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write the body for a section titled '{title}' "
                    f"in the '{day_heading}' block.\n\n"
                    f"Content guidance: {instruction}"
                ),
            }
        ],
    )
    return response.content[0].text.strip()


def _rewrite_section(heading_text: str, existing_body: str, instruction: str) -> str:
    """Rewrite an existing section body per the given instruction."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_SECTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": existing_body,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Rewrite the body of section '{heading_text}' "
                            f"following this instruction: {instruction}"
                        ),
                    },
                ],
            }
        ],
    )
    return response.content[0].text.strip()


def edit_procedure_doc(
    customer_name: str,
    instructions: str,
    existing_md: str,
    output_writer: OutputWriter,
) -> tuple[Path, Path]:
    """Apply natural-language edit instructions to an existing procedure document.

    Two-phase approach to minimise token usage:
    1. Planning: sends only the section heading outline → JSON edit plan (~1 k tokens).
    2. Execution: targeted per-section Claude calls for add/modify; pure Python for remove.

    No full-document round-trips and no output-token continuation loops required.

    Args:
        customer_name:  Customer name (used for output filenames).
        instructions:   Natural-language description of the changes to make.
        existing_md:    Full Markdown text of the current procedure document.
        output_writer:  OutputWriter instance for file I/O.

    Returns:
        Tuple of (markdown_path, pdf_path).
    """
    log.info("Editing procedure doc for %s — instructions: %.120s", customer_name, instructions)

    sections = _parse_sections(existing_md)

    # Phase 1 — plan (cheap: heading outline only)
    try:
        ops = _plan_edits(instructions, sections)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error("Edit planning call returned invalid JSON: %s", exc)
        raise ValueError(f"Edit planning failed — Claude response was not valid JSON: {exc}") from exc

    log.info("Edit plan: %d op(s)\n%s", len(ops), json.dumps(ops, indent=2))

    # Phase 2 — execute each op
    for op in ops:
        op_type = op.get("op")

        if op_type == "remove":
            heading = op["heading"]
            idx = _find_h2(sections, heading)
            if idx >= 0:
                log.info("Removed section: '%s'", sections[idx].heading_text)
                sections.pop(idx)
            else:
                log.warning("remove: no H2 section matched '%s'", heading)

        elif op_type == "modify":
            heading = op["heading"]
            instruction = op["instruction"]
            idx = _find_h2(sections, heading)
            if idx >= 0:
                s = sections[idx]
                new_body = _rewrite_section(s.heading_text, s.body, instruction)
                sections[idx] = replace(s, body="\n" + new_body + "\n\n")
                log.info("Modified section: '%s'", s.heading_text)
            else:
                log.warning("modify: no H2 section matched '%s'", heading)

        elif op_type == "add":
            day_heading = op.get("day_heading", "")
            after_heading = op.get("after_heading")
            title = op["title"]
            instruction = op["instruction"]

            new_body = _write_section(title, day_heading, instruction)

            # Determine insertion index
            insert_at: int | None = None
            if after_heading:
                ah_idx = _find_h2(sections, after_heading)
                if ah_idx >= 0:
                    insert_at = ah_idx + 1
                else:
                    log.warning(
                        "add: after_heading '%s' not found — appending to day block", after_heading
                    )

            if insert_at is None:
                dh_idx = _find_h1(sections, day_heading)
                if dh_idx >= 0:
                    insert_at = next(
                        (i for i in range(dh_idx + 1, len(sections)) if sections[i].level == 1),
                        len(sections),
                    )
                else:
                    insert_at = len(sections)

            # Insert with a placeholder number; _renumber_day_sections fixes ordering after all ops
            heading_text = f"0. {title}"
            new_section = _DocSection(
                heading_line=f"## {heading_text}\n",
                heading_text=heading_text,
                level=2,
                body="\n" + new_body + "\n\n",
            )
            sections.insert(insert_at, new_section)
            log.info("Added section '%s' at index %d (will be renumbered)", title, insert_at)

        else:
            log.warning("Unknown op type '%s' — skipping", op_type)

    # Phase 3 — renumber, reassemble, write
    sections = _renumber_day_sections(sections)
    md_text = _sections_to_md(sections).strip()

    safe_name = customer_name.replace(" ", "_")
    md_path = output_writer.write_text(f"{safe_name}_procedure.md", md_text)
    log.info("Edited Markdown written to %s", md_path)

    pdf_path = output_writer.path(f"{safe_name}_procedure.pdf")
    markdown_to_pdf(md_text, pdf_path, customer_name)
    log.info("Edited PDF written to %s", pdf_path)

    return md_path, pdf_path


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------

# Colours (RGB tuples)
_DARK_BLUE = (31, 78, 121)      # #1F4E79
_MID_BLUE = (46, 117, 182)      # #2E75B6
_WHITE = (255, 255, 255)
_LIGHT_GREY = (240, 240, 240)
_BLACK = (0, 0, 0)
_RULE_GREY = (180, 180, 180)

_PAGE_W = 210   # A4 mm
_PAGE_H = 297
_MARGIN = 15
_USABLE_W = _PAGE_W - 2 * _MARGIN


class _ProcedurePDF(FPDF):
    """fpdf2 subclass with custom header and footer."""

    def __init__(self, customer_name: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.customer_name = customer_name
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_font("Helvetica", style="I", size=8)
        self.set_text_color(*_MID_BLUE)
        self.cell(0, 5, self.customer_name, align="R")
        self.ln(2)
        self.set_text_color(*_BLACK)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")
        self.set_text_color(*_BLACK)


def markdown_to_pdf(md_text: str, output_path: Path, customer_name: str) -> None:
    """Convert Markdown text to a styled A4 PDF using fpdf2."""
    pdf = _ProcedurePDF(customer_name)
    pdf.add_page()

    first_h1 = True
    lines = md_text.splitlines()

    for line in lines:
        # H1
        if line.startswith("# ") and not line.startswith("## "):
            if not first_h1:
                pdf.add_page()
            first_h1 = False
            text = _sanitize(line[2:].strip())
            pdf.set_fill_color(*_DARK_BLUE)
            pdf.set_text_color(*_WHITE)
            pdf.set_font("Helvetica", style="B", size=18)
            pdf.cell(_USABLE_W, 12, text, border=0, fill=True, ln=True)
            pdf.set_text_color(*_BLACK)
            pdf.ln(3)

        # H2
        elif line.startswith("## ") and not line.startswith("### "):
            text = _sanitize(line[3:].strip())
            pdf.set_fill_color(*_MID_BLUE)
            pdf.set_text_color(*_WHITE)
            pdf.set_font("Helvetica", style="B", size=14)
            pdf.cell(_USABLE_W, 9, text, border=0, fill=True, ln=True)
            pdf.set_text_color(*_BLACK)
            pdf.ln(2)

        # H3
        elif line.startswith("### "):
            text = _sanitize(line[4:].strip())
            pdf.set_font("Helvetica", style="BU", size=11)
            pdf.set_text_color(*_DARK_BLUE)
            pdf.cell(_USABLE_W, 7, text, border=0, ln=True)
            pdf.set_text_color(*_BLACK)
            pdf.ln(1)

        # Horizontal rule
        elif line.strip() == "---":
            pdf.ln(2)
            pdf.set_draw_color(*_RULE_GREY)
            pdf.set_line_width(0.4)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.line(x, y, x + _USABLE_W, y)
            pdf.set_line_width(0.2)
            pdf.ln(4)

        # Bullet list item
        elif re.match(r"^[-*] ", line):
            text = _sanitize(line[2:].strip())
            pdf.set_font("Helvetica", size=10)
            pdf.set_x(_MARGIN + 8)
            pdf.cell(5, 5, "-", ln=False)
            pdf.multi_cell(_USABLE_W - 13, 5, text, border=0)

        # Numbered step
        elif re.match(r"^\d+\. ", line):
            pdf.set_font("Helvetica", size=10)
            pdf.set_x(_MARGIN + 8)
            match = re.match(r"^(\d+\.) (.+)", line)
            if match:
                num, text = match.group(1), _sanitize(match.group(2))
                pdf.cell(8, 5, num, ln=False)
                pdf.multi_cell(_USABLE_W - 16, 5, text, border=0)
            else:
                pdf.multi_cell(_USABLE_W - 8, 5, _sanitize(line[2:].strip()), border=0)

        # Code block (4 spaces or tab indent)
        elif line.startswith("    ") or line.startswith("\t"):
            code_text = _sanitize(line.lstrip("\t").lstrip("    "))
            pdf.set_fill_color(*_LIGHT_GREY)
            pdf.set_font("Courier", size=9)
            pdf.set_x(_MARGIN)
            pdf.cell(_USABLE_W, 5, code_text, border=0, fill=True, ln=True)

        # Empty line
        elif line.strip() == "":
            pdf.ln(3)

        # Regular paragraph text
        else:
            pdf.set_font("Helvetica", size=10)
            pdf.set_x(_MARGIN)
            pdf.multi_cell(_USABLE_W, 5, _sanitize(line), border=0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
