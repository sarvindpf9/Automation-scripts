---
name: pdf-renderer
description: "Use this skill when modifying or extending the procedure document PDF renderer in sow_mcp/generators/procedure_doc.py. Covers: Platform9 visual theme constants, markdown element parsing, rendering rules for all element types, and pitfalls observed during development and testing."
---

# PDF Renderer Skill — Platform9 Procedure Document

## Trigger

Use this skill when:
- Modifying `markdown_to_pdf()` or any helper in `procedure_doc.py`
- Adding a new element type to the renderer
- Changing theme colours, font sizes, or spacing
- Debugging visual artefacts in generated PDFs

---

## Platform9 Visual Theme Constants

Extracted from the PF9 RCA reference document. Use these verbatim — do not approximate.

```python
# RGB tuples for fpdf2
_PF9_BLUE   = (0, 137, 199)    # #0089C7 — H2 banners, H3 text, header rule, blockquote accent
_PF9_NAVY   = (14, 17, 53)     # #0E1135 — H1 banners, H4 text, table header row background
_PF9_BODY   = (60, 60, 87)     # #3C3C57 — all body paragraph text
_PF9_WHITE  = (255, 255, 255)
_TBL_ALT    = (237, 245, 250)  # #EDF5FA — alternating table row fill (odd rows)
_CODE_BG    = (244, 244, 246)  # #F4F4F6 — fenced code block fill
_CALLOUT_BG = (249, 249, 249)  # #F9F9F9 — blockquote / note box background
_BORDER     = (221, 221, 221)  # #DDDDDD — table grid lines, callout box borders

# Font sizes (pt)
_FS_H1     = 16   # H1 banner title
_FS_H2     = 13   # H2 section banner
_FS_H3     = 11   # H3 subsection heading
_FS_H4     = 10   # H4 phase/part heading (bold italic)
_FS_BODY   = 10   # body text, bullets, numbered items
_FS_CODE   =  9   # fenced code blocks (Courier)
_FS_FOOTER =  8   # header/footer labels

# Line heights (mm)
_LH_BODY = 5.5
_LH_CODE = 4.2
```

---

## Architecture: Two-Pass Rendering

The renderer uses a two-pass approach to avoid the limitations of line-by-line parsing.

**Pass 1 — `_parse_md_elements(md)`**: Parse the full markdown string into a flat list of typed element dicts. This is the only place where markdown structure is interpreted.

**Pass 2 — `markdown_to_pdf()` loop**: Iterate the element list and render each element. No markdown interpretation in the render pass — only styling decisions.

**Why this matters:** A line-by-line renderer cannot handle:
- Multi-line fenced code blocks (state must be tracked across lines)
- Markdown tables (all rows must be collected before the table can be drawn)
- Indented code fences inside numbered list steps (e.g. `   ```bash`)

---

## Element Types and Rendering Rules

| Element | How rendered | Notes |
|---|---|---|
| `h1` | New page + navy banner, white text, 16pt bold | First H1 does NOT add page |
| `h2` | PF9_BLUE banner, white text, 13pt bold, 3mm top gap | Always on same page as preceding content |
| `h3` | PF9_BLUE text, 11pt bold, thin blue underline rule (45% width) | 2mm top gap |
| `h4` | PF9_NAVY text, 10pt bold italic | Phase/Part sub-headings inside procedure steps |
| `hr` | Thin BORDER-colour horizontal rule, 4mm bottom gap | Section separator |
| `blank` | `ln(2)` — consecutive blanks suppressed by `prev_blank` flag | |
| `code` | Courier 9pt, CODE_BG fill, indented box with padding rows | `_sanitize` (not `_md`): `--now` must render literally |
| `table` | Navy header via FontFace, alternating TBL_ALT rows, fpdf2 table() | Uses fpdf2 2.7+ table() context manager |
| `blockquote` | CALLOUT_BG fill, 3mm left blue accent bar, italic 9pt | Height pre-calculated with `split_only=True` |
| `checklist` | Courier `[ ]`/`[x]` marker, body text in Helvetica | markdown=True for body text |
| `bullet` | `-` leader, indented, multi_cell with markdown=True | Indent level from leading spaces (//2) |
| `numbered` | `N.` leader (7mm), multi_cell with markdown=True | Indent level from leading spaces (//4) |
| `para` | Plain Helvetica multi_cell, markdown=True | Continuation text renders here |

---

## The `_sanitize` / `_md` Distinction

**Critical pitfall:** fpdf2's `markdown=True` in `multi_cell` treats `--` (double dash) as an **underline toggle**. Text after `--` will be underlined until the next `--` or end of string.

**Rule:** Always use `_md(text)` — not `_sanitize(text)` — when passing text to `multi_cell(..., markdown=True)`.

```python
def _md(text: str) -> str:
    """Sanitize + escape fpdf2 markdown triggers."""
    return _MD_ESCAPE_RE.sub(" - ", _sanitize(text))

# _MD_ESCAPE_RE = re.compile(r"--")
```

**When to use `_sanitize` directly** (bypasses `_md` escaping):
- Code block lines: `--now`, `--login` must render literally, not become ` - now`
- Heading text passed to `pdf.cell()`: no markdown parsing, `--` is safe

**The em-dash fix:** `_UNICODE_REPLACEMENTS` maps `—` → ` - ` (space-hyphen-space), NOT `--`. This is the root cause prevention; `_md()` is the belt-and-suspenders catch for any `--` that Claude may write directly.

---

## Fenced Code Block Parser — Indent Awareness

Code fences inside numbered list steps are indented:

```markdown
3. Enable iscsid:
   ```bash
   sudo systemctl enable --now iscsid
   ```
```

The fence marker `   ```bash` has 3 spaces of leading indent. The naive `re.match(r"^```", line)` fails to detect it.

**Fix in `_parse_md_elements`:**

```python
fence_m = re.match(r"^(\s*)(`{3,}|~{3,})\s*(\w*)", line)
if fence_m:
    fence_indent = fence_m.group(1)   # "   "
    fence_chars  = fence_m.group(2)   # "```"
    lang         = fence_m.group(3)   # "bash"
    ...
    # Strip the opening indent from each code line
    if fence_indent and cl.startswith(fence_indent):
        cl = cl[len(fence_indent):]
```

The closing fence is matched with `re.match(rf"^\s*{fence_pat}", cl)` — also indent-tolerant.

---

## Blockquote Rendering

Blockquotes use a two-draw approach to get the left accent bar aligned with the background:

1. Pre-calculate block height using `multi_cell(split_only=True)` (deprecated but reliable for height measurement).
2. Draw `CALLOUT_BG` filled rectangle at `(_MARGIN, y0, _USABLE_W, block_h)`.
3. Draw `PF9_BLUE` filled accent bar at `(_MARGIN, y0, 3, block_h)` — overlays left edge of background.
4. Render text starting at `_MARGIN + 5` (5mm from left, behind accent bar).

The blockquote detector handles leading whitespace (indented `> ` inside numbered steps):

```python
bq_m = re.match(r"^\s*>(.*)", line)
```

Without this, `   > **Note:**` (3-space indent inside a numbered step) would fall through to `para`.

---

## Table Rendering

Uses fpdf2 2.7+ `table()` context manager with `FontFace` for row styling:

```python
from fpdf.table import FontFace

hdr_style = FontFace(fill_color=_PF9_NAVY, color=_PF9_WHITE, emphasis="BOLD", size_pt=9)
alt_style  = FontFace(fill_color=_TBL_ALT)

with pdf.table(width=_USABLE_W, line_height=_LH_BODY, padding=2, borders_layout="ALL") as table:
    row_obj = table.row(style=hdr_style)
    for h in headers:
        row_obj.cell(_sanitize(h))       # No markdown in table cells
    for ri, row_data in enumerate(rows):
        row_obj = table.row(style=alt_style if ri % 2 == 1 else None)
        for cell_text in padded_row:
            row_obj.cell(_sanitize(cell_text))
```

Table cells use `_sanitize` (not `_md`) because fpdf2's table() does not use `markdown=True`.

**Separator row detection** — table parser must skip the `|---|---|` separator line:

```python
def _is_table_separator(row: str) -> bool:
    return bool(re.match(r"^\s*\|?(\s*:?-{1,}:?\s*\|?)+\s*$", row))
```

---

## Header and Footer Design

```
Header:  "Platform9  |  <CustomerName> -- Deployment Procedure"   [PF9_BLUE bold, 8pt]
         <thin PF9_BLUE horizontal rule>

Footer:  "Platform9 Confidential"   [left, gray 8pt]   "Page N"  [right, gray 8pt]
```

The header string uses literal `--` (hardcoded) which is safe because `pdf.cell()` does not apply markdown parsing.

Top margin is 18mm. `set_auto_page_break(auto=True, margin=22)` ensures 22mm bottom clearance for the footer.

---

## `_sanitize` Character Map

| Unicode | Replaced with | Reason |
|---|---|---|
| `—` | ` - ` | em dash — NOT `--` (fpdf2 underline trigger) |
| `–` | `-` | en dash |
| `'` `'` | `'` | curly single quotes |
| `"` `"` | `"` | curly double quotes |
| `…` | `...` | ellipsis |
| `•` | `*` | bullet |
| `→` | `->` | right arrow |
| `←` | `<-` | left arrow |
| `≤` | `<=` | less-than-or-equal (renders as `?` without this) |
| `≥` | `>=` | greater-than-or-equal |
| `≠` | `!=` | not equal |
| `×` | `x` | multiplication sign |
| `°` | ` deg` | degree |
| `\xa0` | ` ` | non-breaking space |

Any character not in this map or latin-1 is replaced with `?` by the `.encode("latin-1", errors="replace")` call. When Claude generates new section content, instruct it to use ASCII equivalents (the `_SECTION_SYSTEM` prompt already does this).

---

## Consecutive Blank Line Suppression

The render loop tracks `prev_blank: bool`. When a `blank` element is encountered and `prev_blank` is already `True`, the `ln(2)` call is skipped. This eliminates the large vertical gaps that appeared in the previous line-by-line renderer when Claude generated two or more blank lines between sections.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| No inline code monospace | `` `code` `` in body text renders with backtick chars in Helvetica. fpdf2 markdown=True does not support backtick spans. Code blocks (fenced) are rendered correctly. |
| Continuation text indent | Text lines indented below a numbered step (e.g. "Then create/edit...") render at the left margin as plain paragraphs, not indented. |
| Table cell markdown | Bold `**text**` inside table cells is not rendered — table cells use `_sanitize` not `_md`. |
| Latin-1 only | fpdf2 Helvetica/Courier are latin-1 fonts. All unsupported characters become `?`. Use Pandoc for full Unicode fidelity. |

---

## Regenerating a PDF After Renderer Changes

```bash
cd hackathon-mcp-sow
.venv/bin/python -c "
from pathlib import Path
from sow_mcp.generators.procedure_doc import markdown_to_pdf

md = Path('output/<CUSTOMER>/<CUSTOMER>_procedure.md').read_text()
markdown_to_pdf(md, Path('output/<CUSTOMER>/<CUSTOMER>_procedure.pdf'), '<CUSTOMER>')
print('Done')
"
open output/<CUSTOMER>/<CUSTOMER>_procedure.pdf
```
