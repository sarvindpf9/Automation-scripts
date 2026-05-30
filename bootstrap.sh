#!/usr/bin/env bash
# bootstrap.sh — set up agent-config-repo and all tool symlinks for this workspace.
# Run once after cloning Automation-scripts on a new machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CONFIG_DIR="$REPO_ROOT/agent-config-repo"

# Override by exporting AGENT_CONFIG_URL before running, or edit this line.
AGENT_CONFIG_URL="${AGENT_CONFIG_URL:-<AGENT_CONFIG_REPO_URL>}"

# Symlinks: <link path in repo> → <target relative to repo root>
declare -A SYMLINKS=(
    [".claude"]="agent-config-repo/claude/.claude/"
    [".agents"]="agent-config-repo/codex/.agents/"
    [".codex"]="agent-config-repo/codex/.codex"
    ["CLAUDE.md"]="agent-config-repo/claude/CLAUDE.md"
    ["AGENTS.md"]="agent-config-repo/codex/AGENTS.md"
    ["CODEX.md"]="agent-config-repo/codex/CODEX.md"
)

# ── 1. Clone agent-config-repo ──────────────────────────────────────────────
if [[ -d "$AGENT_CONFIG_DIR/.git" ]]; then
    echo "✓ agent-config-repo already present"
else
    if [[ "$AGENT_CONFIG_URL" == "<AGENT_CONFIG_REPO_URL>" ]]; then
        echo "ERROR: agent-config-repo not found and no URL configured." >&2
        echo "  Set AGENT_CONFIG_URL env var or edit bootstrap.sh with the remote URL." >&2
        exit 1
    fi
    echo "Cloning agent-config-repo from $AGENT_CONFIG_URL ..."
    git clone "$AGENT_CONFIG_URL" "$AGENT_CONFIG_DIR"
fi

# ── 2. Verify / create all symlinks ─────────────────────────────────────────
ERRORS=0
for LINK in "${!SYMLINKS[@]}"; do
    TARGET="${SYMLINKS[$LINK]}"
    LINK_PATH="$REPO_ROOT/$LINK"

    if [[ -L "$LINK_PATH" ]]; then
        CURRENT_TARGET=$(readlink "$LINK_PATH")
        if [[ "$CURRENT_TARGET" == "$TARGET" ]]; then
            echo "✓ $LINK → $TARGET"
        else
            echo "WARNING: $LINK points to unexpected target: $CURRENT_TARGET (expected: $TARGET)" >&2
            ERRORS=$((ERRORS + 1))
        fi
    elif [[ -e "$LINK_PATH" ]]; then
        echo "ERROR: $LINK exists but is not a symlink — cannot create. Remove it and re-run." >&2
        ERRORS=$((ERRORS + 1))
    else
        echo "Creating $LINK → $TARGET"
        ln -s "$TARGET" "$LINK_PATH"
    fi
done

if [[ "$ERRORS" -gt 0 ]]; then
    echo ""
    echo "Bootstrap completed with $ERRORS warning(s). Review the output above." >&2
    exit 1
fi

# ── 3. Smoke-check skill files are accessible ───────────────────────────────
SKILL_COUNT=$(find "$REPO_ROOT/.claude/skills" -name 'SKILL.md' 2>/dev/null | wc -l | tr -d ' ')
if [[ "$SKILL_COUNT" -eq 0 ]]; then
    echo "ERROR: No SKILL.md files found under .claude/skills — check agent-config-repo." >&2
    exit 1
fi

echo ""
echo "Bootstrap complete."
echo "  Claude skills : $SKILL_COUNT skill(s) in .claude/skills/"
echo "  Settings      : .claude/settings.json"
echo "  Local settings: .claude/settings.local.json (machine-local, not committed)"
