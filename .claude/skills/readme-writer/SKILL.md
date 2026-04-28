---
name: readme-writer
description: "Use this skill when the user asks to write, create, or update a README for a script, tool, or module. Triggers: 'write readme', 'update readme', 'document this script', 'add readme for'. Reads the target script, infers purpose/usage/args, then writes or patches README.md in the same directory."
---

# README Writer Skill

## Behavior

- If `README.md` exists in the script's directory → update only the relevant section(s).
- If it does not exist → create it from scratch.
- Infer all content from the script itself. Never invent values.
- If the script's purpose is ambiguous, ask one question before proceeding.

## Output Format

The format below matches the `cdrom-attach-script` README conventions and is the canonical template for this repo.

````markdown
# <directory-or-module-name>

One-line description of what the script/tool does. Written as a sentence, not a heading.

---

## `<script-filename.sh>`

Brief description: what the script does and its entry-point behaviour (1–2 sentences).

**Dependencies (local):**
- `<tool>`, `<tool>` — what each is used for
- Any credential or access requirements

**Dependencies (hypervisor / remote host):**
- Tools required on the remote side
- Mount paths, services, or sudo requirements

**What it does:**

1. Step one (resolve / lookup)
2. Step two (pre-check)
3. Step three (operation)
...

### Usage

```bash
# <Action description>
./<script>.sh \
  --flag1 <VALUE> \
  --flag2 <VALUE>

# <Second action description>
./<script>.sh \
  --flag1 <VALUE> \
  --flag3 <VALUE>
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `--flag VALUE` | Yes / No / attach only / etc. | What it does |

### Examples

```bash
# Concrete real-world invocation with inline comment
./<script>.sh \
  --flag1 value \
  --flag2 value
```

### <Behaviour sub-topic 1>

Prose explanation of a non-obvious operational behaviour (device allocation, retry logic, etc.).

### Pre-check behaviour

| Check | Applies to |
|-------|-----------|
| Description of check | attach + detach / attach only / etc. |

### <Compatibility or constraint topic>

Prose on architecture or environment constraints that affect usage.

#### <Sub-variant A>

Details, code blocks, or `openstack` commands needed for this variant.

#### Verification

```
<example command and expected output showing the operation succeeded>
```

#### Example outputs

```
<raw terminal output — no bash highlighting, verbatim session transcript>
```
````

## Formatting Rules

These rules are derived from the existing `cdrom-attach-script/README.md` and must be followed:

1. **Top-level heading (`#`)** is the directory/module name, not the script filename.
2. **Script filename** is an `##` heading wrapped in backticks: `## \`script.sh\``.
3. **Dependency blocks** use bold labels (`**Dependencies (local):**`) as inline sub-headings, not `###` headings.
4. **"What it does"** is a bold inline label followed by a numbered list — not a heading.
5. **Options table** has three columns only: `Flag | Required | Description`. No `Default` column; embed the default in the Description cell if needed.
6. **Usage examples** each start with a `# Comment` line inside the code block describing the action before the invocation.
7. **Pre-check table** uses two columns: `Check | Applies to`. Values in "Applies to" are `attach + detach`, `attach only`, or `detach only`.
8. **Example outputs** use plain fenced code blocks (no language tag) — they are verbatim terminal transcripts, not bash source.
9. **Horizontal rule** (`---`) separates the top-level description from the `##` script section.
10. **No `Default` column** in the options table and no `## Notes` or `## Purpose` headings — those concepts are embedded inline.

## Steps Claude Must Follow

1. Read the target script fully.
2. Identify: purpose, entrypoint, flags/args, local and remote deps, pre-checks, exit conditions.
3. Check if `README.md` exists in the same directory.
4. If exists: locate the relevant `##` section by script filename heading and patch it. Do not touch other sections.
5. If not exists: write full README using the format above.
6. Verify every flag name, default value, and behaviour claim against the actual script source — do not invent any.
7. Write the file. Confirm path and whether it was created or updated.

## Constraints

- Do not invent flag names, defaults, or behaviour not present in the code.
- Do not add forward-looking sections ("Future Work", "Roadmap").
- Do not add a `## Notes` or `## Purpose` top-level section — fold that content into the script's `##` section prose.
- Keep it ops-relevant: focus on invocation, deps, failure modes, and compatibility constraints.