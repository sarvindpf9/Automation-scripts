---
name: remote-task-runner
description: "Use this skill when the user asks Codex to run a command, script, Terraform command, or Ansible command on a remote Linux host over SSH. Delegates execution to claude-automation/remote-agent.py, enforces destructive-command guardrails before connecting, avoids logging passwords, and returns concise stdout/stderr plus exit status."
---

# Remote Task Runner

## When To Use

Use this for SSH job execution on a remote host:

- Inline shell checks, e.g. `hostname`, `df -h`, `systemctl status <unit>`.
- Remote `.sh` or `.py` scripts already present on the host.
- Terraform subcommands from a remote working directory.
- Ansible ad-hoc or playbook commands from a remote working directory.

Do not use this for long-lived daemons, interactive TUI programs, bulk file sync, or destructive maintenance unless the user explicitly asks and the guardrails allow it.

## Required Inputs

Ask one focused question if any required value is missing.

```text
SSH_HOST=<HOSTNAME_OR_IP>
SSH_USER=<SSH_USER>
REMOTE_DIR=<ABSOLUTE_REMOTE_WORKING_DIRECTORY>
TASK_TYPE=bash|script|python|terraform|ansible
TASK=<COMMAND_OR_REMOTE_SCRIPT_OR_SUBCOMMAND>
TASK_ARGS=<OPTIONAL_ARGS>
```

Password handling:

- Prefer key-based SSH when available.
- If password auth is required, use `SSH_PASS` only as an environment variable for the runner.
- Never print, summarize, store, or include the password in final output.

Host memory:

- The runner persists successful connection profiles with `name`, `SSH_HOST`, `SSH_USER`, `REMOTE_DIR`, and `TASK_TYPE` entries in `~/.remote-task-history.json`.
- If `SSH_HOST`, `SSH_USER`, or `REMOTE_DIR` are omitted, run `python3 claude-automation/remote-agent.py --history-json` before asking the user.
- Reuse a saved profile only when the user names it or when exactly one recent profile is unambiguous for the request. If multiple profiles could apply, ask one focused question.
- Use `--use-last` for non-interactive reuse of the newest saved profile, or `--profile '<PROFILE_NAME>'` for a named profile.
- Never store `SSH_PASS`; ask for it again or rely on key-based SSH.

## Resolve Command

Build exactly one remote command:

```text
bash      -> <TASK> <TASK_ARGS>
script    -> bash <TASK> <TASK_ARGS>
python    -> python3 <TASK> <TASK_ARGS>
terraform -> terraform <TASK> <TASK_ARGS>
ansible   -> <TASK> <TASK_ARGS>
```

For `TASK_TYPE=ansible`, `TASK` must be the full command, such as:

```bash
ansible all -m ping -i inventory.yaml
ansible-playbook -i inventory.yaml playbooks/site.yml
```

Do not invent remote directories, inventory paths, Terraform var files, project names, or script arguments.

## Guardrails

Check the resolved command before opening SSH. Refuse if it contains:

- `rm -rf`, disk writes to `/dev/*`, `mkfs`, `wipefs`, `shred`.
- `shutdown`, `poweroff`, `halt`, `reboot`, `init 0`, `init 6`.
- Stopping/disabling SSH or network services.
- `iptables -F`, `nft flush ruleset`, or obvious SSH lockout changes.
- `passwd` except `passwd --status`, `userdel`, `groupdel`, `chpasswd`, `usermod -p`.
- `rmmod`, `modprobe -r`.
- `curl|wget ... | bash|sh|python|perl|ruby`.
- `crontab -r`, `kill -9 1`, `killall -9`.
- `terraform destroy`.
- Commands longer than 2048 characters.

For `terraform apply`, require either a reviewed plan file or an explicit narrow target. Otherwise refuse and suggest `terraform plan` first.

## Execution Workflow

1. Verify the runner exists:

   ```bash
   test -f claude-automation/remote-agent.py
   ```

2. Run a dry-run guardrail check first:

   ```bash
   python3 claude-automation/remote-agent.py \
     --host '<SSH_HOST>' \
     --user '<SSH_USER>' \
     --remote-dir '<REMOTE_DIR>' \
     --cmd '<RESOLVED_COMMAND>' \
     --dry-run
   ```

   When reusing history non-interactively, replace `--host/--user/--remote-dir`
   with either `--use-last` or `--profile '<PROFILE_NAME>'`.

3. If the dry run passes, execute:

   ```bash
   SSH_PASS='<SSH_PASS>' python3 claude-automation/remote-agent.py \
     --host '<SSH_HOST>' \
     --user '<SSH_USER>' \
     --remote-dir '<REMOTE_DIR>' \
     --cmd '<RESOLVED_COMMAND>'
   ```

   When reusing history non-interactively, replace `--host/--user/--remote-dir`
   with either `--use-last` or `--profile '<PROFILE_NAME>'`.

The runner handles `expect`, SSH options, command timeout, password redaction, history without passwords, stdout/stderr capture, and exit-code propagation.

If `/usr/bin/expect` is missing or the runner exits non-zero, report the captured output and stop.

After a successful execution, confirm that `~/.remote-task-history.json` contains the host, user, and remote directory for later reuse.

## Local Script Uploads

Only upload a local script when the user explicitly requests it.

Rules:

- `LOCAL_SCRIPT` must be an absolute local path to a regular `.sh` or `.py` file.
- Read the file and run the same guardrail check against its contents before transfer.
- Copy only to `REMOTE_SCRIPT_DIR`, defaulting to `REMOTE_DIR`.
- Use `scp` unless the user requested `rsync`.
- Never honor `../` traversal in the destination basename.

After transfer, run `chmod +x <REMOTE_PATH>`, then resolve command as `script` or `python`.

## Report Format

Keep the final response concise:

```text
Host: <SSH_HOST>
Directory: <REMOTE_DIR>
Command: <RESOLVED_COMMAND>
Exit code: <N>

Summary:
<one to four lines describing success, failure, warnings, or first relevant error>

Output:
<stdout/stderr excerpt or full output when short>
```

For Ansible, include per-host `SUCCESS`, `FAILED`, or `UNREACHABLE` lines when present. For Terraform, include the plan/apply resource counts or the first error line.
