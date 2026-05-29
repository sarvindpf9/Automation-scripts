#!/usr/bin/env python3
"""
remote-agent.py — Execute user-supplied commands on a remote host via SSH.

Guardrails block destructive operations before any SSH connection is made.
Previously used host/user/remote-dir are remembered across sessions in
~/.remote-task-history.json. Passwords are never written to disk.

Usage (fully interactive — prompts for everything):
    python3 remote-agent.py

Usage (partial — supply what you know, prompted for the rest):
    python3 remote-agent.py --host 10.96.10.171 --cmd 'ansible all -m ping -i inventory.yaml'

Usage (non-interactive, password via env):
    SSH_PASS=secret python3 remote-agent.py --host HOST --user USER \
        --remote-dir DIR --cmd 'CMD'

Dry-run (guardrail check only, no SSH):
    python3 remote-agent.py --dry-run
"""

from __future__ import annotations

import argparse
import getpass
import json
from datetime import datetime, timezone
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Session history — persists host/user/remote-dir (never password)
# ---------------------------------------------------------------------------

_HISTORY_FILE = Path.home() / ".remote-task-history.json"


def _normalize_history_entry(entry: dict) -> dict:
    """Return a consistent in-memory history entry shape."""
    return {
        "name": entry.get("name", ""),
        "timestamp": entry.get("timestamp", ""),
        "SSH_HOST": entry.get("SSH_HOST", entry.get("host", "")),
        "SSH_USER": entry.get("SSH_USER", entry.get("user", "ubuntu")),
        "REMOTE_DIR": entry.get(
            "REMOTE_DIR",
            entry.get("remote_dir", "/home/ubuntu"),
        ),
        "TASK_TYPE": entry.get("TASK_TYPE", entry.get("task_type", "bash")),
        "LOCAL_SCRIPT": entry.get("LOCAL_SCRIPT"),
    }


def load_history_entries() -> list[dict]:
    """Return all saved connection profiles in newest-first order."""
    try:
        if _HISTORY_FILE.exists():
            raw = json.loads(_HISTORY_FILE.read_text())
            if isinstance(raw, list):
                return [
                    _normalize_history_entry(entry)
                    for entry in raw
                    if isinstance(entry, dict)
                ]
            if isinstance(raw, dict):
                return [_normalize_history_entry(raw)]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def load_history() -> dict:
    """Return most-recent entry as a normalized dict with keys host/user/remote_dir."""
    entries = load_history_entries()
    if not entries:
        return {}

    entry = entries[0]
    return {
        "host": entry.get("SSH_HOST", ""),
        "user": entry.get("SSH_USER", "ubuntu"),
        "remote_dir": entry.get("REMOTE_DIR", "/home/ubuntu"),
        "name": entry.get("name", ""),
    }


def _history_entry_matches(old_entry: dict, new_entry: dict) -> bool:
    """Return True when an old entry should be replaced by a new save."""
    old_name = old_entry.get("name", "")
    new_name = new_entry.get("name", "")
    if old_name and new_name:
        return old_name == new_name
    return (
        old_entry.get("SSH_HOST") == new_entry.get("SSH_HOST")
        and old_entry.get("SSH_USER") == new_entry.get("SSH_USER")
        and old_entry.get("REMOTE_DIR") == new_entry.get("REMOTE_DIR")
    )


def save_history(
    host: str,
    user: str,
    remote_dir: str,
    task_type: str = "bash",
    name: str = "",
) -> None:
    entry = {
        "name": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "SSH_HOST": host,
        "SSH_USER": user,
        "REMOTE_DIR": remote_dir,
        "TASK_TYPE": task_type,
        "LOCAL_SCRIPT": None,
    }
    try:
        existing = load_history_entries()
        deduped = [
            old_entry
            for old_entry in existing
            if not _history_entry_matches(old_entry, entry)
        ]
        deduped.insert(0, entry)
        _HISTORY_FILE.write_text(json.dumps(deduped[:20], indent=2))
        _HISTORY_FILE.chmod(0o600)
    except OSError:
        pass


def forget_history_profile(name: str) -> bool:
    """Remove a named profile. Returns True when an entry was removed."""
    entries = load_history_entries()
    kept = [entry for entry in entries if entry.get("name") != name]
    if len(kept) == len(entries):
        return False

    try:
        _HISTORY_FILE.write_text(json.dumps(kept, indent=2))
        _HISTORY_FILE.chmod(0o600)
        return True
    except OSError:
        return False


def find_history_entry(name: str = "", use_last: bool = False) -> Optional[dict]:
    """Find a saved connection profile by name or return the newest entry."""
    entries = load_history_entries()
    if name:
        for entry in entries:
            if entry.get("name") == name:
                return entry
        return None
    if use_last and entries:
        return entries[0]
    return None


def format_history(entries: list[dict], json_output: bool = False) -> str:
    """Render saved connection history for humans or automation."""
    if json_output:
        return json.dumps(entries, indent=2)
    if not entries:
        return "No remote-task history found."

    rows = ["Saved remote-task connection profiles:"]
    for index, entry in enumerate(entries, start=1):
        name = entry.get("name") or "-"
        rows.append(
            f"{index:>2}. {name:<20} "
            f"{entry.get('SSH_USER', 'ubuntu')}@{entry.get('SSH_HOST', '')} "
            f"-> {entry.get('REMOTE_DIR', '/home/ubuntu')} "
            f"({entry.get('TASK_TYPE', 'bash')})"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Guardrail definitions
# ---------------------------------------------------------------------------

_DENY_PATTERNS: list[tuple[str, str]] = [
    # Filesystem destruction
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b", "recursive force delete (rm -rf / rm -fr)"),
    (r"\bdd\b.*\bof=/dev/", "raw disk write via dd"),
    (r"\bmkfs\b", "filesystem format (mkfs)"),
    (r"\bwipefs\b", "filesystem signature wipe (wipefs)"),
    (r"\bshred\b", "secure file overwrite (shred)"),
    # Power / boot
    (r"\b(shutdown|poweroff|halt|reboot)\b", "system power/reboot command"),
    (r"\binit\s+[06]\b", "init runlevel 0 or 6 (shutdown/reboot)"),
    (r"\bsystemctl\s+(reboot|poweroff|halt|kexec)\b", "systemctl power command"),
    # Critical service disruption
    (r"\bsystemctl\s+stop\s+(ssh|sshd|networking|network|NetworkManager)\b",
     "stopping SSH or networking service"),
    (r"\bsystemctl\s+disable\s+(ssh|sshd|networking|network|NetworkManager)\b",
     "disabling SSH or networking service"),
    # Firewall flush (locks out SSH)
    (r"\biptables\s+-F\b", "iptables flush all rules"),
    (r"\bnft\s+flush\s+ruleset\b", "nftables flush ruleset"),
    # Account / credential manipulation
    (r"\bpasswd\b(?!\s+--status)", "password change (passwd)"),
    (r"\buserdel\b", "user deletion (userdel)"),
    (r"\bchpasswd\b", "bulk password change (chpasswd)"),
    # Kernel / module danger
    (r"\brmmod\b|\bmodprobe\s+-r\b", "kernel module removal"),
    # Pipe from internet into shell (supply-chain risk)
    (r"(curl|wget)\s+.*\|\s*(bash|sh|python3?|perl|ruby)\b",
     "piping remote script directly into interpreter"),
    # Crontab wipe
    (r"\bcrontab\s+-r\b", "crontab removal (crontab -r)"),
    # Overwrite device nodes
    (r">\s*/dev/(?!null|zero)", "redirect output to a device node"),
    # Kill all or kill PID 1
    (r"\bkill\s+-9\s+1\b|\bkillall\s+-9\b", "kill PID-1 or killall -9"),
    # Terraform destroy
    (r"\bterraform\s+destroy\b", "terraform destroy (use plan -destroy to preview)"),
    # Group and account manipulation
    (r"\bgroupdel\b", "group deletion (groupdel)"),
    (r"\busermod\s+.*-p\b", "inline password hash set (usermod -p)"),
]

_COMPILED_DENY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.IGNORECASE), reason)
    for pat, reason in _DENY_PATTERNS
]

_MAX_CMD_LEN = 2048


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    host: str
    user: str
    password: str
    cmd: str
    remote_dir: str
    dry_run: bool
    profile_name: str = ""


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    blocked: bool = False
    block_reason: str = ""
    lines: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.blocked


# ---------------------------------------------------------------------------
# Interactive input resolution
# ---------------------------------------------------------------------------

def _prompt(label: str, default: Optional[str] = None, secret: bool = False) -> str:
    """Prompt the user for a value. Returns stripped input or default."""
    hint = f" [{default}]" if default else ""
    display = f"{label}{hint}: "
    while True:
        if secret:
            val = getpass.getpass(display).strip()
        else:
            val = input(display).strip()
        if val:
            return val
        if default is not None:
            return default
        print("  (required — please enter a value)")


def _confirm(question: str) -> bool:
    """Ask a yes/no question. Default is yes."""
    ans = input(f"{question} [Y/n]: ").strip().lower()
    return ans in ("", "y", "yes")


def resolve_config(args: argparse.Namespace) -> AgentConfig:
    """
    Merge CLI args, session history, and interactive prompts into a final
    AgentConfig. History is shown and confirmed (or replaced) before use.
    """
    selected_history = find_history_entry(args.profile, args.use_last)
    if (args.profile or args.use_last) and not selected_history:
        selector = f"profile '{args.profile}'" if args.profile else "last profile"
        raise ValueError(f"No saved remote-task history entry found for {selector}.")

    history = {
        "host": selected_history.get("SSH_HOST", ""),
        "user": selected_history.get("SSH_USER", "ubuntu"),
        "remote_dir": selected_history.get("REMOTE_DIR", "/home/ubuntu"),
        "name": selected_history.get("name", ""),
    } if selected_history else load_history()
    use_history = False

    # If the user supplied no connection args at all, offer to reuse history.
    has_host = bool(args.host)
    has_user = bool(args.user)

    if selected_history:
        use_history = True
    elif history and not has_host:
        h_host = history.get("host", "")
        h_user = history.get("user", "ubuntu")
        h_dir  = history.get("remote_dir", "/home/ubuntu")
        print(f"\n  [Memory] Last session: {h_user}@{h_host}  ->  {h_dir}")
        use_history = _confirm("  Reuse this connection profile?")

    # Resolve host
    if args.host:
        host = args.host
    elif use_history:
        host = history["host"]
    else:
        host = _prompt("  Host (IP or hostname)")

    # Resolve user
    if has_user:
        user = args.user
    elif use_history and (selected_history or not has_host):
        # Only reuse the remembered user when the whole block was accepted.
        user = history.get("user", "ubuntu")
    else:
        user = _prompt("  SSH username", default="ubuntu")

    # Resolve remote_dir
    if args.remote_dir:
        remote_dir = args.remote_dir
    elif use_history and (selected_history or not has_host):
        remote_dir = history.get("remote_dir", "/home/ubuntu")
        if not selected_history:
            # Even when reusing history interactively, let the user override the dir.
            override = input(f"  Remote directory [{remote_dir}]: ").strip()
            if override:
                remote_dir = override
    else:
        remote_dir = _prompt("  Remote working directory", default="/home/ubuntu")

    # Resolve password — env var wins; never persisted to history
    password = os.environ.get("SSH_PASS", "")
    if not password and not args.dry_run:
        password = _prompt(f"  SSH password for {user}@{host}", secret=True)

    # Resolve command
    if args.cmd:
        cmd = args.cmd
    else:
        cmd = _prompt("  Command to execute on remote host")

    return AgentConfig(
        host=host,
        user=user,
        password=password,
        cmd=cmd,
        remote_dir=remote_dir,
        dry_run=args.dry_run,
        profile_name=args.save_profile or args.profile or history.get("name", ""),
    )


# ---------------------------------------------------------------------------
# Guardrail check
# ---------------------------------------------------------------------------

def check_guardrails(cmd: str) -> Optional[str]:
    """Return a denial reason string, or None if the command is allowed."""
    if len(cmd) > _MAX_CMD_LEN:
        return f"command exceeds maximum allowed length ({_MAX_CMD_LEN} chars)"
    for pattern, reason in _COMPILED_DENY:
        if pattern.search(cmd):
            return reason
    return None


# ---------------------------------------------------------------------------
# SSH execution via expect
# ---------------------------------------------------------------------------

def _build_expect_script(cfg: AgentConfig) -> str:
    def tcl_quote(s: str) -> str:
        if "{" not in s and "}" not in s:
            return "{" + s + "}"
        escaped = (s.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("$", "\\$")
                    .replace("[", "\\["))
        return '"' + escaped + '"'

    return textwrap.dedent(f"""\
        #!/usr/bin/expect -f
        set timeout 180
        set host       {tcl_quote(cfg.host)}
        set user       {tcl_quote(cfg.user)}
        set pass       {tcl_quote(cfg.password)}
        set remote_dir {tcl_quote(cfg.remote_dir)}
        set cmd        {tcl_quote(cfg.cmd)}

        spawn ssh -o StrictHostKeyChecking=no \\
                  -o UserKnownHostsFile=/dev/null \\
                  -o LogLevel=ERROR \\
                  $user@$host

        # Handle password prompt OR key-based login transparently.
        expect {{
            "password:"     {{ send "$pass\\r"; exp_continue }}
            -re {{[\\$#] ?}} {{ }}
            timeout         {{ puts stderr "ERROR: SSH connection timed out"; exit 1 }}
            eof             {{ puts stderr "ERROR: SSH refused or host unreachable"; exit 1 }}
        }}

        send "cd $remote_dir && $cmd; echo __EXIT__:\\$?\\r"

        set exit_code 0
        expect {{
            -re {{__EXIT__:(\\d+)}} {{
                set exit_code $expect_out(1,string)
            }}
            eof {{
                puts stderr "ERROR: SSH connection closed unexpectedly"
                exit 3
            }}
            timeout {{
                puts stderr "ERROR: command timed out (180s)"
                exit 2
            }}
        }}

        send "exit\\r"
        expect eof
        exit $exit_code
    """)


def run_remote(cfg: AgentConfig) -> RunResult:
    script_content = _build_expect_script(cfg)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".exp", delete=False, prefix="remote_agent_"
    ) as f:
        f.write(script_content)
        tmp_path = f.name

    try:
        os.chmod(tmp_path, stat.S_IRWXU)
        result = subprocess.run(
            ["/usr/bin/expect", "-f", tmp_path],
            capture_output=True,
            text=True,
            timeout=210,
        )
        return RunResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            lines=result.stdout.splitlines(),
        )
    except subprocess.TimeoutExpired:
        return RunResult(exit_code=2, stdout="", stderr="Local timeout waiting for expect process")
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_ANSIBLE_STATUS_RE = re.compile(
    r"^(?P<host>\S+)\s+\|\s+(?P<status>SUCCESS|FAILED|UNREACHABLE)(?:\s+=>\s+\{)?",
    re.MULTILINE,
)


def _parse_ansible_hosts(text: str) -> list[dict]:
    rows = []
    for m in _ANSIBLE_STATUS_RE.finditer(text):
        block_start = m.end()
        snippet = text[block_start : block_start + 300]
        ping_match = re.search(r'"ping":\s*"(\w+)"', snippet)
        msg = ping_match.group(1) if ping_match else "—"
        rows.append({"host": m.group("host"), "status": m.group("status"), "msg": msg})
    return rows


def print_report(cfg: AgentConfig, result: RunResult) -> None:
    sep = "-" * 60
    print(f"\n{'='*60}")
    print("  Remote Agent — Execution Report")
    print(f"{'='*60}")
    print(f"  Host      : {cfg.host}")
    print(f"  Directory : {cfg.remote_dir}")
    print(f"  Command   : {cfg.cmd}")
    print(f"  Dry-run   : {cfg.dry_run}")
    print(f"  Exit code : {result.exit_code}")

    if result.blocked:
        print(f"\n  [BLOCKED] {result.block_reason}")
        print(sep)
        return

    hosts = _parse_ansible_hosts(result.stdout)
    if hosts:
        print(f"\n  Per-host results:")
        col_w = max(len(r["host"]) for r in hosts) + 2
        print(f"  {'Host':<{col_w}} {'Status':<14} Message")
        print(f"  {'-'*col_w} {'-'*14} -------")
        for r in hosts:
            print(f"  {r['host']:<{col_w}} {r['status']:<14} {r['msg']}")

    print(f"\n  Raw output:\n{sep}")
    clean = re.sub(re.escape(cfg.password), "[REDACTED]", result.stdout) if cfg.password else result.stdout
    print(clean.rstrip())

    if result.stderr.strip():
        print(f"\n  Stderr:\n{sep}")
        clean_err = re.sub(re.escape(cfg.password), "[REDACTED]", result.stderr) if cfg.password else result.stderr
        print(clean_err.rstrip())

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Execute a user-supplied command on a remote host with guardrails.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            All arguments are optional — you will be prompted for anything not supplied.
            Previously used host/user/remote-dir are remembered in ~/.remote-task-history.json.
            Passwords are never stored; supply via SSH_PASS env var or interactive prompt.

            Guardrails block:
              - Recursive/force deletes, disk writes, filesystem formats
              - System shutdown/reboot commands
              - Stopping SSH or network services
              - Firewall flushes, user deletion, password changes
              - Piping remote scripts into an interpreter
        """),
    )
    p.add_argument("--host",       default=None, help="Remote host IP or hostname")
    p.add_argument("--user",       default=None, help="SSH username")
    p.add_argument("--remote-dir", default=None, dest="remote_dir",
                   help="Working directory on the remote host")
    p.add_argument("--cmd",        default=None, help="Command to run on the remote host")
    p.add_argument("--dry-run",    action="store_true",
                   help="Validate and print the command without executing")
    p.add_argument("--history", action="store_true",
                   help="Print saved connection profiles and exit")
    p.add_argument("--history-json", action="store_true",
                   help="Print saved connection profiles as JSON and exit")
    p.add_argument("--use-last", action="store_true",
                   help="Reuse the latest saved host/user/remote-dir non-interactively")
    p.add_argument("--profile", default=None,
                   help="Reuse a named saved connection profile")
    p.add_argument("--save-profile", default="",
                   help="Save or update this profile name after a successful SSH session")
    p.add_argument("--forget-profile", default="",
                   help="Remove a named saved connection profile and exit")
    return p.parse_args()


def infer_task_type(cmd: str) -> str:
    """Infer a coarse task type from the command prefix for history display."""
    cmd_stripped = cmd.lstrip()
    if cmd_stripped.startswith("ansible"):
        return "ansible"
    if cmd_stripped.startswith("terraform"):
        return "terraform"
    if cmd_stripped.startswith("python"):
        return "python"
    return "bash"


def reached_remote_shell(result: RunResult) -> bool:
    """Return True when expect reached the remote shell and command sentinel."""
    if "__EXIT__:" in result.stdout:
        return True
    connection_errors = (
        "SSH connection timed out",
        "SSH refused or host unreachable",
        "SSH connection closed unexpectedly",
    )
    return result.exit_code == 0 and not any(
        error in result.stderr for error in connection_errors
    )


def main() -> int:
    args = parse_args()

    if args.history or args.history_json:
        print(format_history(load_history_entries(), args.history_json))
        return 0

    if args.forget_profile:
        removed = forget_history_profile(args.forget_profile)
        if removed:
            print(f"Removed remote-task profile: {args.forget_profile}")
            return 0
        print(f"No remote-task profile found: {args.forget_profile}")
        return 1

    try:
        cfg = resolve_config(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 130

    # Guardrail check — always runs, even in dry-run mode.
    denial = check_guardrails(cfg.cmd)
    if denial:
        result = RunResult(exit_code=1, stdout="", stderr="",
                           blocked=True, block_reason=denial)
        print_report(cfg, result)
        return 1

    if cfg.dry_run:
        print(f"\n[DRY-RUN] Command passed guardrails.")
        print(f"  Host      : {cfg.host}")
        print(f"  User      : {cfg.user}")
        print(f"  Directory : {cfg.remote_dir}")
        print(f"  Command   : {cfg.cmd}")
        return 0

    result = run_remote(cfg)
    if reached_remote_shell(result):
        save_history(
            cfg.host,
            cfg.user,
            cfg.remote_dir,
            infer_task_type(cfg.cmd),
            cfg.profile_name,
        )
    print_report(cfg, result)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
