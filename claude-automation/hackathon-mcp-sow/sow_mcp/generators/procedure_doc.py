"""Generate a Day0/Day1/Day2 deployment procedure document using Claude."""

from __future__ import annotations

import json
import logging
import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import anthropic
from fpdf import FPDF
from fpdf.table import FontFace

from ..output_writer import OutputWriter

log = logging.getLogger(__name__)

_UNICODE_REPLACEMENTS = str.maketrans(
    {
        "—": " - ",  # em dash  (NOT "--": fpdf2 markdown=True treats "--" as underline toggle)
        "–": "-",    # en dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2026": "...",  # ellipsis
        "\u2022": "*",    # bullet
        "\u2192": "->",   # right arrow
        "\u2190": "<-",   # left arrow
        "\u2264": "<=",   # less-than-or-equal
        "\u2265": ">=",   # greater-than-or-equal
        "\u2260": "!=",   # not equal
        "\u00d7": "x",    # multiplication sign
        "\u00b0": " deg", # degree
        "\xa0": " ",     # non-breaking space
    }
)

# fpdf2 2.7+ markdown triggers are ** (bold), __ (underline), ~~ (strikethrough).
# Standalone "--" (e.g. in prose) is escaped; CLI flags like --now / --format are preserved.
_MD_ESCAPE_RE = re.compile(r"--(?![a-zA-Z0-9-])")

# Inline code spans: `cmd` → rendered as bold so they stand out in body text.
# fpdf2 multi_cell(markdown=True) has no backtick support; bold is the closest visual proxy.
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _sanitize(text: str) -> str:
    """Replace non-latin-1 characters that core PDF fonts cannot encode."""
    return text.translate(_UNICODE_REPLACEMENTS).encode("latin-1", errors="replace").decode("latin-1")


def _md(text: str) -> str:
    """Sanitize, highlight inline code spans, and escape fpdf2 markdown triggers."""
    text = _sanitize(text)
    text = _INLINE_CODE_RE.sub(r"**\1**", text)
    return _MD_ESCAPE_RE.sub(" - ", text)


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

{env_context_block}Rules:
- Never write placeholder markers (e.g. <PLACEHOLDER>, [VALUE], <IP_ADDRESS>) anywhere in the output.
  For any environment-specific value not listed in the environment context above, use natural
  descriptive text instead (e.g. "the management VIP", "the configured DNS server IP").
- Each Procedure section must have numbered steps. Each step is one atomic action.
- Verification sections must list specific commands or checks with expected output.
- Rollback sections must be present in Day 1 sections. If true rollback is not possible, state that and describe the impact.
- Draw content from the provided documentation. Do not invent technical details not supported by the docs.
- Use fenced code blocks (```bash or ```text) for all commands — never inline them in prose.
"""


def generate_procedure_doc(
    customer_name: str,
    docs: list[dict],
    output_writer: OutputWriter,
    reference_urls: list[str] | None = None,
    env_context: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    """
    Synthesize a Day0/Day1/Day2 procedure document from reference docs.

    Args:
        customer_name:   Customer name for headers and filenames.
        docs:            List of {"filename", "path", "text"} dicts from docs_reader.
        output_writer:   OutputWriter instance for file I/O.
        reference_urls:  Optional list of reference URLs (appended as footnotes only).
        env_context:     Dict of environment-specific values to inject into the document
                         (e.g. {"management_vip": "10.0.0.10", "dns_servers": "10.0.0.53"}).

    Returns:
        Tuple of (markdown_path, pdf_path).
    """
    today = date.today().isoformat()

    if env_context:
        filled = {k: v for k, v in env_context.items() if v and v.strip()}
        if filled:
            env_lines = "\n".join(
                f"  - {k.replace('_', ' ').title()}: {v}" for k, v in filled.items()
            )
            env_context_block = (
                "Environment-specific values for this deployment "
                "(use these directly in all commands, configs, and descriptions):\n"
                f"{env_lines}\n\n"
            )
        else:
            env_context_block = ""
    else:
        env_context_block = ""

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        customer_name=customer_name,
        today=today,
        env_context_block=env_context_block,
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
        max_tokens=2048,
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
- Never write placeholder markers (e.g. <PLACEHOLDER>, <IP_ADDRESS>, [VALUE]) in the output.
  For unknown environment-specific values, use descriptive text (e.g. "the management VIP").
- All commands must be in fenced code blocks (```bash or ```text).
- Output Markdown only — no surrounding prose, no horizontal rules at start/end.
"""


def _write_section(title: str, day_heading: str, instruction: str) -> str:
    """Generate body content for a brand-new section."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
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
        max_tokens=4096,
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

    # Phase 2a — pre-fetch all API-bound results in parallel.
    # modify/add each require an API call; remove is pure Python.
    # We snapshot section bodies now (before any mutations) so parallel reads are safe.
    # Insertion indices for add ops are recomputed at apply time (after removes may shift them).
    api_tasks: list[tuple[int, str, tuple]] = []  # (op_idx, op_type, call_args)
    for i, op in enumerate(ops):
        op_type = op.get("op")
        if op_type == "modify":
            idx = _find_h2(sections, op["heading"])
            if idx >= 0:
                s = sections[idx]
                api_tasks.append((i, "modify", (s.heading_text, s.body, op["instruction"])))
            else:
                log.warning("modify: no H2 section matched '%s' — skipping", op["heading"])
        elif op_type == "add":
            api_tasks.append((i, "add", (op["title"], op.get("day_heading", ""), op["instruction"])))

    api_results: dict[int, str] = {}
    if api_tasks:
        log.info("Dispatching %d section API call(s) in parallel", len(api_tasks))
        with ThreadPoolExecutor(max_workers=min(len(api_tasks), 5)) as executor:
            future_to_idx = {
                executor.submit(
                    _rewrite_section if op_type == "modify" else _write_section,
                    *args,
                ): i
                for i, op_type, args in api_tasks
            }
            for future in as_completed(future_to_idx):
                op_idx = future_to_idx[future]
                try:
                    api_results[op_idx] = future.result()
                    log.info("Section API call completed for op %d", op_idx)
                except Exception as exc:
                    log.error("Section API call failed for op %d: %s", op_idx, exc)
                    raise ValueError(
                        f"Section generation failed during edit (op {op_idx}): {exc}"
                    ) from exc

    # Phase 2b — apply ops sequentially so index arithmetic stays correct.
    # Removes may shift indices; inserts recompute their position at apply time.
    for i, op in enumerate(ops):
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
            if i not in api_results:
                continue  # heading was not found at pre-fetch time; already warned
            heading = op["heading"]
            idx = _find_h2(sections, heading)
            if idx >= 0:
                s = sections[idx]
                sections[idx] = replace(s, body="\n" + api_results[i] + "\n\n")
                log.info("Modified section: '%s'", s.heading_text)
            else:
                log.warning("modify: section '%s' not found at apply time", heading)

        elif op_type == "add":
            if i not in api_results:
                continue
            day_heading = op.get("day_heading", "")
            after_heading = op.get("after_heading")
            title = op["title"]

            # Recompute insertion index now (after any preceding removes)
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
                        (j for j in range(dh_idx + 1, len(sections)) if sections[j].level == 1),
                        len(sections),
                    )
                else:
                    insert_at = len(sections)

            heading_text = f"0. {title}"
            new_section = _DocSection(
                heading_line=f"## {heading_text}\n",
                heading_text=heading_text,
                level=2,
                body="\n" + api_results[i] + "\n\n",
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
# PDF renderer — Platform9 visual theme
# ---------------------------------------------------------------------------

# Platform9 theme colours (RGB tuples; extracted from PF9 RCA reference doc)
_PF9_BLUE   = (0, 137, 199)    # #0089C7 — H2 banner, H3 text, header rule
_PF9_NAVY   = (14, 17, 53)     # #0E1135 — H1 banner, H4 text, table headers
_PF9_BODY   = (60, 60, 87)     # #3C3C57 — body paragraph text
_PF9_WHITE  = (255, 255, 255)
_TBL_ALT    = (237, 245, 250)  # #EDF5FA — alternating table row fill
_CODE_BG    = (244, 244, 246)  # #F4F4F6 — code block background
_CALLOUT_BG = (249, 249, 249)  # #F9F9F9 — blockquote / note box background
_BORDER     = (221, 221, 221)  # #DDDDDD — table and callout borders

_PAGE_W   = 210   # A4 mm
_PAGE_H   = 297
_MARGIN   = 18
_USABLE_W = _PAGE_W - 2 * _MARGIN

# Font sizes (pt)
_FS_H1     = 16
_FS_H2     = 13
_FS_H3     = 11
_FS_H4     = 10
_FS_BODY   = 10
_FS_CODE   =  9
_FS_FOOTER =  8

# Line heights (mm)
_LH_BODY = 5.5
_LH_CODE = 4.2


class _ProcedurePDF(FPDF):
    """fpdf2 subclass with Platform9-branded header and footer."""

    def __init__(self, customer_name: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.customer_name = customer_name
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=22)

    def header(self) -> None:
        self.set_font("Helvetica", style="B", size=8)
        self.set_text_color(*_PF9_BLUE)
        label = f"Platform9  |  {self.customer_name} -- Deployment Procedure"
        self.cell(_USABLE_W, 5, label, align="L")
        self.ln(1)
        # Thin blue rule
        self.set_draw_color(*_PF9_BLUE)
        self.set_line_width(0.4)
        self.line(_MARGIN, self.get_y(), _MARGIN + _USABLE_W, self.get_y())
        self.set_line_width(0.2)
        self.set_draw_color(0, 0, 0)
        self.ln(3)
        self.set_text_color(*_PF9_BODY)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", size=_FS_FOOTER)
        self.set_text_color(160, 160, 160)
        self.cell(_USABLE_W / 2, 5, "Platform9 Confidential", align="L")
        self.cell(_USABLE_W / 2, 5, f"Page {self.page_no()}", align="R")
        self.set_text_color(*_PF9_BODY)


# ---------------------------------------------------------------------------
# Markdown element parser
# ---------------------------------------------------------------------------

def _is_table_separator(row: str) -> bool:
    """True if row is a markdown table separator line (|---|:---:|...)."""
    return bool(re.match(r"^\s*\|?(\s*:?-{1,}:?\s*\|?)+\s*$", row))


def _parse_row(row: str) -> list[str]:
    return [c.strip() for c in row.strip("|").split("|")]


def _parse_md_elements(md: str) -> list[dict]:
    """Parse markdown into a flat list of typed element dicts.

    Handles: h1-h4, hr, blank, code (fenced), table, blockquote,
             checklist, bullet, numbered, para.
    Fence detection is indent-aware so code blocks nested inside
    numbered steps are captured correctly.
    """
    elements: list[dict] = []
    lines = md.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block (indent-aware: "   ```bash" is valid) ───────
        fence_m = re.match(r"^(\s*)(`{3,}|~{3,})\s*(\w*)", line)
        if fence_m:
            fence_indent = fence_m.group(1)
            fence_chars  = fence_m.group(2)
            lang         = fence_m.group(3)
            fence_pat    = re.escape(fence_chars)
            code_lines: list[str] = []
            i += 1
            while i < len(lines):
                cl = lines[i]
                if re.match(rf"^\s*{fence_pat}", cl):
                    i += 1
                    break
                # Strip the opening fence's indentation from each code line
                if fence_indent and cl.startswith(fence_indent):
                    cl = cl[len(fence_indent):]
                code_lines.append(cl)
                i += 1
            elements.append({"type": "code", "lang": lang, "lines": code_lines})
            continue

        # ── Markdown table ─────────────────────────────────────────────────
        if line.startswith("|"):
            tbl_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            if len(tbl_lines) >= 2:
                headers = _parse_row(tbl_lines[0])
                rows = [
                    _parse_row(r)
                    for r in tbl_lines[1:]
                    if not _is_table_separator(r)
                ]
                elements.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # ── Headings ──────────────────────────────────────────────────────
        m = re.match(r"^# (?!#)(.+)", line)
        if m:
            elements.append({"type": "h1", "text": m.group(1).strip()})
            i += 1
            continue

        m = re.match(r"^## (?!#)(.+)", line)
        if m:
            elements.append({"type": "h2", "text": m.group(1).strip()})
            i += 1
            continue

        m = re.match(r"^### (?!#)(.+)", line)
        if m:
            elements.append({"type": "h3", "text": m.group(1).strip()})
            i += 1
            continue

        m = re.match(r"^#{4}\s+(.+)", line)
        if m:
            elements.append({"type": "h4", "text": m.group(1).strip()})
            i += 1
            continue

        # ── Horizontal rule ───────────────────────────────────────────────
        if re.match(r"^---+\s*$", line):
            elements.append({"type": "hr"})
            i += 1
            continue

        # ── Blockquote (handles leading whitespace: "   > Note:") ──────────
        bq_m = re.match(r"^\s*>(.*)", line)
        if bq_m:
            text = bq_m.group(1).lstrip()
            i += 1
            while i < len(lines):
                bq_cont = re.match(r"^\s*>(.*)", lines[i])
                if bq_cont:
                    text += " " + bq_cont.group(1).lstrip()
                    i += 1
                else:
                    break
            elements.append({"type": "blockquote", "text": text.strip()})
            continue

        # ── Checklist item ────────────────────────────────────────────────
        m = re.match(r"^(\s*)- \[([ xX])\] (.+)", line)
        if m:
            indent = len(m.group(1)) // 2
            elements.append({
                "type": "checklist",
                "text": m.group(3).strip(),
                "checked": m.group(2).lower() == "x",
                "indent": indent,
            })
            i += 1
            continue

        # ── Bullet ────────────────────────────────────────────────────────
        m = re.match(r"^(\s*)[-*+] (.+)", line)
        if m:
            indent = len(m.group(1)) // 2
            elements.append({"type": "bullet", "text": m.group(2).strip(), "indent": indent})
            i += 1
            continue

        # ── Numbered list item ────────────────────────────────────────────
        m = re.match(r"^(\s*)(\d+)\. (.+)", line)
        if m:
            indent = len(m.group(1)) // 4
            elements.append({
                "type": "numbered",
                "num": m.group(2),
                "text": m.group(3).strip(),
                "indent": indent,
            })
            i += 1
            continue

        # ── Blank line ────────────────────────────────────────────────────
        if line.strip() == "":
            elements.append({"type": "blank"})
            i += 1
            continue

        # ── Regular paragraph (incl. indented continuation lines) ─────────
        elements.append({"type": "para", "text": line.strip()})
        i += 1

    return elements


# ---------------------------------------------------------------------------
# PDF element renderers
# ---------------------------------------------------------------------------

def _render_code_block(pdf: FPDF, lines: list[str]) -> None:
    """Render a fenced code block with gray fill, Courier font, and a border rect."""
    pdf.ln(1)
    pdf.set_font("Courier", size=_FS_CODE)
    pdf.set_fill_color(*_CODE_BG)
    pdf.set_text_color(*_PF9_NAVY)

    x0 = _MARGIN + 2
    w  = _USABLE_W - 4

    # Top padding
    pdf.set_x(x0)
    pdf.cell(w, 1.5, "", fill=True, new_x="LMARGIN", new_y="NEXT")

    for code_line in lines:
        pdf.set_x(x0 + 2)
        pdf.multi_cell(
            w - 2, _LH_CODE, _sanitize(code_line),
            fill=True, border=0, align="L",
            new_x="LMARGIN", new_y="NEXT",
        )

    # Bottom padding
    pdf.set_x(x0)
    pdf.cell(w, 1.5, "", fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(*_PF9_BODY)
    pdf.ln(2)


def _render_table(pdf: FPDF, headers: list[str], rows: list[list[str]]) -> None:
    """Render a markdown table with navy header row and alternating body rows."""
    pdf.ln(2)
    n_cols = max(len(headers), 1)

    # Proportional column widths based on max content length; minimum 15mm per column
    max_lens = [max(len(h), 4) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:n_cols]):
            if i < len(max_lens):
                max_lens[i] = max(max_lens[i], len(cell))
    total_len = sum(max_lens) or n_cols
    col_widths = [max(15, int(l / total_len * _USABLE_W)) for l in max_lens]
    # Assign any rounding remainder to the last column
    col_widths[-1] = max(15, _USABLE_W - sum(col_widths[:-1]))

    hdr_style = FontFace(
        fill_color=_PF9_NAVY,
        color=_PF9_WHITE,
        emphasis="BOLD",
        size_pt=_FS_BODY - 1,
    )
    alt_style = FontFace(fill_color=_TBL_ALT)
    pdf.set_draw_color(*_BORDER)
    pdf.set_font("Helvetica", size=_FS_BODY - 1)
    with pdf.table(
        width=_USABLE_W,
        col_widths=col_widths,
        line_height=_LH_BODY,
        padding=2,
        borders_layout="ALL",
    ) as table:
        row_obj = table.row(style=hdr_style)
        for h in headers:
            row_obj.cell(_sanitize(h))
        for ri, row_data in enumerate(rows):
            padded = (row_data + [""] * n_cols)[:n_cols]
            style  = alt_style if ri % 2 == 1 else None
            row_obj = table.row(style=style)
            for cell_text in padded:
                row_obj.cell(_sanitize(cell_text))
    pdf.set_draw_color(0, 0, 0)
    pdf.set_font("Helvetica", size=_FS_BODY)
    pdf.ln(2)


def _render_blockquote(pdf: FPDF, text: str) -> None:
    """Render a blockquote as a callout box with a left blue accent bar."""
    pdf.ln(1)
    pdf.set_font("Helvetica", style="I", size=_FS_BODY - 1)
    pdf.set_text_color(*_PF9_NAVY)

    w_text = _USABLE_W - 6  # text column starts 6mm from left margin

    # Measure height using split_only (deprecated but reliable for height calc)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        wrapped = pdf.multi_cell(w_text, _LH_BODY - 0.5, _md(text), split_only=True)
    block_h = len(wrapped) * (_LH_BODY - 0.5) + 4  # 4mm total vertical padding

    y0 = pdf.get_y()

    # Callout background
    pdf.set_fill_color(*_CALLOUT_BG)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(_MARGIN, y0, _USABLE_W, block_h, style="FD")

    # Left accent bar
    pdf.set_fill_color(*_PF9_BLUE)
    pdf.rect(_MARGIN, y0, 3, block_h, style="F")

    # Text (1.5mm vertical padding, 6mm left offset)
    pdf.set_xy(_MARGIN + 5, y0 + 2)
    pdf.multi_cell(
        w_text, _LH_BODY - 0.5, _md(text),
        fill=False, border=0, align="L",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_y(y0 + block_h + 2)
    pdf.set_text_color(*_PF9_BODY)
    pdf.set_draw_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def markdown_to_pdf(md_text: str, output_path: Path, customer_name: str) -> None:
    """Convert Markdown to a styled A4 PDF using the Platform9 visual theme.

    Two-pass approach: parse the markdown into typed elements first, then
    render each element with appropriate styling.  This handles fenced code
    blocks (including indented fences inside numbered steps), markdown tables,
    H4 phase headings, checklist items, and blockquote callouts — none of which
    a line-by-line renderer can process correctly.
    """
    pdf = _ProcedurePDF(customer_name)
    pdf.add_page()

    elements  = _parse_md_elements(md_text)
    first_h1  = True
    prev_blank = False  # suppress consecutive blank lines

    for el in elements:
        t = el["type"]

        # ── Blank ─────────────────────────────────────────────────────────
        if t == "blank":
            if not prev_blank:
                pdf.ln(2)
            prev_blank = True
            continue
        prev_blank = False

        # ── H1 — new page + navy banner ───────────────────────────────────
        if t == "h1":
            if not first_h1:
                # Only force a new page when the current page is mostly full;
                # otherwise continue on the same page to avoid half-blank pages.
                remaining = pdf.h - pdf.get_y() - 22  # 22 mm bottom margin
                if remaining < 70:
                    pdf.add_page()
                else:
                    pdf.ln(12)
            first_h1 = False
            text = _sanitize(el["text"])
            pdf.set_fill_color(*_PF9_NAVY)
            pdf.set_text_color(*_PF9_WHITE)
            pdf.set_font("Helvetica", style="B", size=_FS_H1)
            pdf.cell(_USABLE_W, 12, text, border=0, fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_PF9_BODY)
            pdf.ln(4)

        # ── H2 — blue banner ──────────────────────────────────────────────
        elif t == "h2":
            pdf.ln(3)
            text = _sanitize(el["text"])
            pdf.set_fill_color(*_PF9_BLUE)
            pdf.set_text_color(*_PF9_WHITE)
            pdf.set_font("Helvetica", style="B", size=_FS_H2)
            pdf.cell(_USABLE_W, 9, text, border=0, fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_PF9_BODY)
            pdf.ln(3)

        # ── H3 — bold blue with underline rule ────────────────────────────
        elif t == "h3":
            pdf.ln(2)
            text = _sanitize(el["text"])
            pdf.set_font("Helvetica", style="B", size=_FS_H3)
            pdf.set_text_color(*_PF9_BLUE)
            pdf.cell(_USABLE_W, 6, text, border=0, new_x="LMARGIN", new_y="NEXT")
            y = pdf.get_y()
            pdf.set_draw_color(*_PF9_BLUE)
            pdf.set_line_width(0.3)
            pdf.line(_MARGIN, y, _MARGIN + _USABLE_W * 0.45, y)
            pdf.set_line_width(0.2)
            pdf.set_draw_color(0, 0, 0)
            pdf.set_text_color(*_PF9_BODY)
            pdf.ln(2)

        # ── H4 — bold italic navy (phase / part sub-headings) ─────────────
        elif t == "h4":
            pdf.ln(2)
            text = _sanitize(el["text"])
            pdf.set_font("Helvetica", style="BI", size=_FS_H4)
            pdf.set_text_color(*_PF9_NAVY)
            pdf.cell(_USABLE_W, 6, text, border=0, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_PF9_BODY)
            pdf.ln(1)

        # ── Horizontal rule ───────────────────────────────────────────────
        elif t == "hr":
            pdf.ln(2)
            pdf.set_draw_color(*_BORDER)
            pdf.set_line_width(0.3)
            pdf.line(_MARGIN, pdf.get_y(), _MARGIN + _USABLE_W, pdf.get_y())
            pdf.set_line_width(0.2)
            pdf.set_draw_color(0, 0, 0)
            pdf.ln(4)

        # ── Fenced code block ─────────────────────────────────────────────
        elif t == "code":
            _render_code_block(pdf, el["lines"])

        # ── Table ─────────────────────────────────────────────────────────
        elif t == "table":
            _render_table(pdf, el["headers"], el["rows"])

        # ── Blockquote callout ────────────────────────────────────────────
        elif t == "blockquote":
            _render_blockquote(pdf, el["text"])

        # ── Checklist item — rendered as a bullet (checkboxes suppressed) ───
        elif t == "checklist":
            indent = el.get("indent", 0)
            x_off  = _MARGIN + 5 + indent * 5
            pdf.set_font("Helvetica", size=_FS_BODY)
            pdf.set_text_color(*_PF9_BODY)
            pdf.set_x(x_off)
            pdf.cell(4, _LH_BODY, "-", new_x="RIGHT", new_y="TOP")
            avail_w = _MARGIN + _USABLE_W - x_off - 4
            pdf.multi_cell(
                avail_w, _LH_BODY, _md(el["text"]),
                fill=False, border=0, align="L",
                markdown=True, new_x="LMARGIN", new_y="NEXT",
            )

        # ── Bullet ────────────────────────────────────────────────────────
        elif t == "bullet":
            indent = el.get("indent", 0)
            x_off  = _MARGIN + 5 + indent * 5
            pdf.set_font("Helvetica", size=_FS_BODY)
            pdf.set_text_color(*_PF9_BODY)
            pdf.set_x(x_off)
            pdf.cell(4, _LH_BODY, "-", new_x="RIGHT", new_y="TOP")
            avail_w = _MARGIN + _USABLE_W - x_off - 4
            pdf.multi_cell(
                avail_w, _LH_BODY, _md(el["text"]),
                fill=False, border=0, align="L",
                markdown=True, new_x="LMARGIN", new_y="NEXT",
            )

        # ── Numbered list item ────────────────────────────────────────────
        elif t == "numbered":
            indent = el.get("indent", 0)
            x_off  = _MARGIN + 5 + indent * 8
            label  = f"{el['num']}."
            pdf.set_font("Helvetica", size=_FS_BODY)
            pdf.set_text_color(*_PF9_BODY)
            pdf.set_x(x_off)
            pdf.cell(7, _LH_BODY, label, new_x="RIGHT", new_y="TOP")
            avail_w = _MARGIN + _USABLE_W - x_off - 7
            pdf.multi_cell(
                avail_w, _LH_BODY, _md(el["text"]),
                fill=False, border=0, align="L",
                markdown=True, new_x="LMARGIN", new_y="NEXT",
            )

        # ── Regular paragraph ─────────────────────────────────────────────
        elif t == "para":
            pdf.set_font("Helvetica", size=_FS_BODY)
            pdf.set_text_color(*_PF9_BODY)
            pdf.set_x(_MARGIN)
            pdf.multi_cell(
                _USABLE_W, _LH_BODY, _md(el["text"]),
                fill=False, border=0, align="L",
                markdown=True, new_x="LMARGIN", new_y="NEXT",
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
