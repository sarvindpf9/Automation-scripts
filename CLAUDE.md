i# CLAUDE.md — Infrastructure Automation Repository Context

> **Purpose:** This file is the authoritative context document for Claude when operating as a contributor to this repository. Read this file completely before making any edits, generating code, or answering questions about this codebase. Treat it like an ADR + Makefile combined — it defines *what exists*, *how things are done here*, and *what you must never assume*.

---

## 1. Repository Identity

| Field              | Value                                                                 |
|--------------------|-----------------------------------------------------------------------|
| Repo purpose       | Infrastructure automation for hybrid cloud (AWS + OpenStack) environments |
| Primary languages  | Python 3.11+, Bash (POSIX-compatible), HCL (Terraform ≥ 1.6), YAML (Ansible) |
| Target platforms   | OpenStack (epoxy and above release), AWS, EKS, kubernetes,rancher RHEL 8/9, ubuntu 22/24 LTS Amazon Linux 2023 |
| IaC tool           | Terraform with S3 remote state + DynamoDB locking                    |
| Config management  | Ansible (agentless, SSH-based), roles sourced from internal Galaxy   |
| CI/CD              | GitHub Actions (`.github/workflows/`)                                |
| Secrets management | AWS Secrets Manager (prod), HashiCorp Vault (OpenStack side)         |
| Python venv        | `.venv/` at repo root — **never** use system Python                  |

---

## 2. What Claude Is Authorized to Do

| Action                                      | Authorized? |
|---------------------------------------------|-------------|
| Edit existing scripts and modules           | ✅ Yes       |
| Add new files following existing conventions| ✅ Yes       |
| Write or update tests                       | ✅ Yes       |
| Update documentation and README               | ✅ Yes       |
| Propose new modules or roles                | ✅ With justification |
| Add new provider dependencies               | ⚠️ Propose only — check with user first |
| Delete files                                | ❌ Never without explicit instruction |
| Generate or embed credentials               | ❌ Never     |

---

## 3. Questions Claude Must Ask Before Editing

When a task is ambiguous or the codebase context is incomplete, Claude must ask the following questions **before generating any code**. Do not make assumptions — ask:

1. **Target environment:** "Is this change for dev, staging, or prod? Prod has stricter rules — should I apply those constraints?"
2. **AWS vs OpenStack scope:** "Is this targeting AWS, OpenStack, or both? Some modules exist for one but not the other."
3. **Existing module check:** "Have you checked `terraform/modules/` or `ansible/roles/` for an existing abstraction? I'll search before writing new code."
4. **Naming convention confirmation:** "What is the service/component name? I'll follow the `{env}_{service}_{resource_type}` convention — please confirm the values."
5. **Idempotency requirement:** "Should this script be safe to run multiple times? I'll add idempotency guards if so."
6. **State impact:** "Does this change touch existing Terraform state? If yes, I'll flag any potential resource replacements before writing the plan."
7. **Secret handling:** "Does this involve credentials or sensitive values? I'll  never embed them and would suggest the alternative to safely use. For testing locally I will suggest how to embed and use it."
8. **Test expectation:** "Should I include unit/integration tests for this change? I'll check with you if there is a need for test cases.."

---

## 6. How Claude Should Operate in This Repo

1. **Always read this file first.** If asked to edit code without this context, request it.
2. **Search before writing.** Check for existing modules, roles, and utilities before generating new ones.
3. **Flag unknowns explicitly.** If something about the environment is unclear (flavor names, VPC IDs, bucket prefixes), say so — do not invent plausible values.
4. **Propose, don't apply.** Generate diffs and explain the impact. Do not assume approval to apply.
5. **Minimal blast radius.** Make the smallest correct change. Refactoring unrelated code in the same PR is not permitted.
6. **Document your reasoning.** For non-obvious decisions, add an inline comment explaining why.
7. **Test coverage is  optional.** Every new function, script, or role gets a corresponding test unless the task explicitly says otherwise.

