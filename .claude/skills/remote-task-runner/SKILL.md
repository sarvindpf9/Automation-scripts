---
name: remote-task-runner
description: "SSH to a remote host using password-based auth (via expect) and execute any user-supplied task — bash command, shell script, Python script, Terraform operation, or Ansible ad-hoc/playbook. Optionally copies a local script to the remote host via scp or rsync before execution. Guardrails block all destructive operations before any SSH connection is made. Returns full stdout/stderr, exit code, and a task-type-aware summary."
---

# Remote Task Runner Skill

## Purpose

Connect to a remote host over SSH, execute a user-supplied task in a specified working directory, and report the result. Optionally transfers a local script to the remote host using `scp` or `rsync` (both password-driven via `expect`) before execution. The skill is task-type agnostic: it handles inline commands, local or remote shell scripts, Python scripts, Terraform workflows, and Ansible ad-hoc/playbook commands — with identical guardrail enforcement across all types.

---

## Inputs Required

| Input | Description | Required |
| ----- | ----------- | -------- |
| `SSH_HOST` | IP or hostname of the target host | Yes |
| `SSH_USER` | SSH login username | Yes |
| `SSH_PASS` | SSH password — never logged or displayed | Yes |
| `REMOTE_DIR` | Absolute working directory on the remote host | Yes |
| `TASK_TYPE` | One of: `bash`, `python`, `terraform`, `ansible`, `script` | Yes |
| `TASK` | The command, script path, or playbook to run (see per-type details below). When `LOCAL_SCRIPT` is set this is auto-derived and may be omitted. | Conditional |
| `TASK_ARGS` | Optional extra arguments appended to the task invocation | No |
| `LOCAL_SCRIPT` | Absolute local path to a `.sh` or `.py` file to copy to the remote before execution | No |
| `TRANSFER_METHOD` | `scp` or `rsync` — controls how `LOCAL_SCRIPT` is transferred. Defaults to `scp`. | No |
| `REMOTE_SCRIPT_DIR` | Remote destination directory for the transferred script. Defaults to `REMOTE_DIR`. | No |

### Connection history

- `remote-agent.py` persists successful connection profiles with `name`, `SSH_HOST`, `SSH_USER`, `REMOTE_DIR`, and `TASK_TYPE` in `~/.remote-task-history.json`.
- If `SSH_HOST`, `SSH_USER`, or `REMOTE_DIR` are omitted, first run `python3 claude-automation/remote-agent.py --history-json`.
- Reuse a saved profile only when the user names it or when exactly one recent profile is unambiguous for the request. If multiple profiles could apply, ask one focused question.
- For non-interactive execution, use `--use-last` for the newest profile or `--profile '<PROFILE_NAME>'` for a named profile instead of prompting.
- Never store or reuse `SSH_PASS`; ask for it again or rely on key-based SSH.

### TASK_TYPE values and what TASK means for each

| TASK_TYPE | What TASK should contain | Example |
| --------- | ------------------------ | ------- |
| `bash` | A single inline shell command or short pipeline | `df -h` |
| `script` | Absolute path to a `.sh` file on the remote host (auto-set when `LOCAL_SCRIPT` is a `.sh` file) | `/home/ubuntu/check-services.sh` |
| `python` | Absolute path to a `.py` file on the remote host (auto-set when `LOCAL_SCRIPT` is a `.py` file) | `/home/ubuntu/scripts/report.py` |
| `terraform` | A `terraform` sub-command (`plan`, `apply -auto-approve`, `output`, `show`) | `plan -var-file=prod.tfvars` |
| `ansible` | A full `ansible` or `ansible-playbook` invocation | `ansible all -m ping -i inventory.yaml` |

---

## Guardrails — Claude Must Enforce These Before Every Execution

Guardrails are checked against the full resolved command string **before** any SSH connection is opened. If any rule matches, Claude must refuse execution and report the specific rule that fired. No exceptions.

### Blocked: Filesystem Destruction

- `rm -rf`, `rm -fr`, `rm -f` targeting non-`/tmp` paths
- `dd if=... of=/dev/<anything>`
- `mkfs`, `wipefs`, `shred`
- `> /dev/<device>` (except `/dev/null` and `/dev/zero`)

### Blocked: System Power and Boot

- `shutdown`, `poweroff`, `halt`, `reboot`, `init 0`, `init 6`
- `systemctl reboot`, `systemctl poweroff`, `systemctl halt`, `systemctl kexec`

### Blocked: Critical Service Disruption

- `systemctl stop <ssh|sshd|networking|network|NetworkManager>`
- `systemctl disable <ssh|sshd|networking|network|NetworkManager>`
- `service <ssh|networking> stop`

### Blocked: Network / Firewall Lockout

- `iptables -F` (flush all rules)
- `nft flush ruleset`
- Any command that would remove the default SSH ingress rule

### Blocked: Account and Credential Manipulation

- `passwd` (without `--status`)
- `userdel`, `groupdel`
- `chpasswd`, `usermod -p`
- Writing to `/etc/shadow`, `/etc/passwd`

### Blocked: Kernel and Module Operations

- `rmmod`, `modprobe -r`
- Writing to `/proc/sys/kernel/sysrq` or similar

### Blocked: Terraform Destructive Sub-commands

- `terraform destroy` (unconditionally blocked; use `plan` to review instead)
- `terraform apply` without explicit `-target` or a reviewed plan file when the diff is unknown

### Blocked: Supply-Chain Execution

- Piping from `curl`, `wget`, `fetch` directly into `bash`, `sh`, `python`, `perl`, `ruby`
- `eval $(...)` patterns fetching from remote URLs

### Blocked: Data Exfiltration Indicators

- Commands redirecting output to external hosts via `nc`, `ncat`, `socat` to non-localhost
- `scp`, `rsync` pushing from the **remote** host to any third host that is not `SSH_HOST` during the session
- Note: inbound transfers **from local to `SSH_HOST`** (the `LOCAL_SCRIPT` copy step) are explicitly allowed and are not subject to this rule

### Blocked: Miscellaneous

- `crontab -r` (wipe all cron jobs)
- `kill -9 1`, `killall -9`
- Commands exceeding 2048 characters (injection surface)

---

## Steps Claude Must Follow

1. **Identify task type.** If `TASK_TYPE` is ambiguous or missing, ask one clarifying question before proceeding.

2. **Handle `LOCAL_SCRIPT` if provided:**

   a. Verify the file exists locally (`test -f <LOCAL_SCRIPT>`). If it does not exist, abort and report the missing path.

   b. Read the file content and run the **same guardrail checks** against it as against the resolved command (step 3). If any rule fires in the script body, abort before any transfer.

   c. Derive the remote destination:
      - `REMOTE_SCRIPT_DIR` defaults to `REMOTE_DIR` if not supplied.
      - Remote path = `<REMOTE_SCRIPT_DIR>/<basename of LOCAL_SCRIPT>`

   d. Auto-derive `TASK_TYPE` and `TASK` when not explicitly set:
      - `.sh` extension → `TASK_TYPE=script`, `TASK=<remote path>`
      - `.py` extension → `TASK_TYPE=python`, `TASK=<remote path>`
      - Any other extension → ask the user which `TASK_TYPE` applies.

   e. **Transfer the file** using an `expect` script:
      - **scp** (default): `scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR <LOCAL_SCRIPT> <SSH_USER>@<SSH_HOST>:<REMOTE_SCRIPT_DIR>/`
      - **rsync**: `rsync -az --checksum -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" <LOCAL_SCRIPT> <SSH_USER>@<SSH_HOST>:<REMOTE_SCRIPT_DIR>/`
      - The expect script handles the `password:` prompt with `<SSH_PASS>` and times out after **60 seconds**.
      - If the transfer exits non-zero, abort and report the transfer error — do not proceed to execution.

   f. After successful transfer, make the script executable on the remote host via a short SSH+expect session:
      - `chmod +x <remote path>`

3. **Resolve the full command string** from `TASK_TYPE`, `TASK`, and `TASK_ARGS`:
   - `bash`      → `<TASK> <TASK_ARGS>`
   - `script`    → `bash <TASK> <TASK_ARGS>`
   - `python`    → `python3 <TASK> <TASK_ARGS>`
   - `terraform` → `terraform <TASK> <TASK_ARGS>`
   - `ansible`   → `<TASK> <TASK_ARGS>` (caller provides full `ansible …` invocation)

4. **Run guardrail check** against the resolved command string. If any rule fires:
   - Print which rule matched and the matched text.
   - Abort. Do not open an SSH connection.

5. **Verify the runner script exists** locally: `claude-automation/remote-agent.py` relative to the repository root (`test -f claude-automation/remote-agent.py`). If missing, abort and report — do not fall back to building inline expect scripts. The script internally checks for `/usr/bin/expect` and will report if it is absent.

6. **Resolve connection history if needed.** If any of `SSH_HOST`, `SSH_USER`, or `REMOTE_DIR` is missing:

   ```bash
   python3 claude-automation/remote-agent.py --history-json
   ```

   Use `--profile '<PROFILE_NAME>'` when the user named a profile. Use `--use-last` only when the newest profile is clearly the intended target. Ask one focused question if multiple saved profiles could apply.

7. **Invoke `remote-agent.py`** via the Bash tool, passing the resolved command as `--cmd` and the password via environment variable only:

   ```bash
   SSH_PASS='<SSH_PASS>' python3 claude-automation/remote-agent.py \
     --host '<SSH_HOST>' \
     --user '<SSH_USER>' \
     --remote-dir '<REMOTE_DIR>' \
     --cmd '<RESOLVED_COMMAND>'
   ```

   When reusing history non-interactively, replace `--host/--user/--remote-dir` with either `--use-last` or `--profile '<PROFILE_NAME>'`.

   - Always pass the password via `SSH_PASS` env var — never as a CLI argument (it would appear in process listings and shell history).
   - The script handles the SSH session (via expect, 180 s timeout), guardrail re-enforcement, history persistence to `~/.remote-task-history.json`, password redaction, and output formatting.
   - Capture stdout and stderr. If the script exits non-zero, include all captured output in the report.
   - Note: `LOCAL_SCRIPT` transfer (steps 2a–2f) is still executed inline via a short expect session, as `remote-agent.py` does not yet accept a `--local-script` argument. Only the main SSH execution delegates to the script.

8. **Parse `remote-agent.py`'s output** to fill in the report sections. The script emits per-host Ansible results and an exit code line. Use its formatted output as the `### Raw output` block; synthesise the `### Summary` section from the exit code and any `error`, `ERROR`, `warning`, or `traceback` lines present in stdout/stderr.

9. Password redaction is handled by `remote-agent.py` internally — no additional scrubbing step needed in the sub-agent.

10. History persistence is handled by `remote-agent.py` internally — no additional write step needed.

11. **Report** using the Output Format below.

---

## Output Format

```
## Remote Task Runner — Result

**Host:**            <SSH_HOST>
**User:**            <SSH_USER>
**Directory:**       <REMOTE_DIR>
**Task type:**       <TASK_TYPE>
**Command:**         <RESOLVED_COMMAND>
**Exit code:**       <N>

### Transfer status  (omit section if LOCAL_SCRIPT was not provided)

**Local file:**      <LOCAL_SCRIPT>
**Method:**          scp | rsync
**Remote dest:**     <REMOTE_SCRIPT_DIR>/<basename>
**Transfer result:** OK (exit 0) — or — FAILED (exit N): <error line>

### Guardrail status

PASSED  — no rules matched
  — or —
BLOCKED — <rule name>: <matched text>

### Summary  (task-type-aware)

#### Ansible
| Host | Status | Message |
| ---- | ------ | ------- |
| <host> | SUCCESS / FAILED / UNREACHABLE | <detail> |

Play recap: ok=N  changed=N  unreachable=N  failed=N

#### Terraform
Plan:  N to add, N to change, N to destroy.
  — or —
Apply complete! Resources: N added, N changed, N destroyed.
  — or —
Error: <first error line>

#### Bash / Script / Python
Exit code: N
Warnings / errors detected:
  - <line>

### Raw output

```
<verbatim stdout + stderr, password redacted>
```
```

---

## Constraints

- `claude-automation/remote-agent.py` is the primary SSH executor for all non-`LOCAL_SCRIPT` tasks. Never build inline expect scripts as a substitute — if the script is missing, abort and tell the user.
- Never log or display `SSH_PASS` anywhere in output — redact every occurrence as `[REDACTED]`.
- Use `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null` to avoid known_hosts friction on lab hosts.
- If the remote command exits non-zero, still capture and return all output — do not abort early.
- For `terraform apply`, always recommend running `terraform plan` first if a plan file is not provided.
- Do not invent or assume values for `REMOTE_DIR`, inventory paths, var files, or script arguments — use exactly what the user supplies or ask.
- If `TASK_TYPE=terraform` and `TASK=destroy`, refuse unconditionally and suggest `terraform plan -destroy` as a safe preview instead.
- `LOCAL_SCRIPT` must be an absolute path to a regular file on the local machine. If the user supplies a relative path, resolve it against CWD and confirm before proceeding.
- Scan `LOCAL_SCRIPT` content through all guardrails before transferring. A script that would be blocked if typed inline is equally blocked when uploaded.
- If `TRANSFER_METHOD=rsync`, verify `rsync` is installed locally (`which rsync`) before building the expect script; fall back to `scp` and notify the user if rsync is absent.
- Never transfer files to a path outside `REMOTE_SCRIPT_DIR` — do not honour `../` traversal in the basename.
