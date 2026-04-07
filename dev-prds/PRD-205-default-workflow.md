---
id: "PRD-205"
title: "Default Workflow + Prompts"
kind: task
status: ready
priority: high
effort: xs
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
  - "[[PRD-202-builtins-registry-stubs]]"
blocks:
  - "[[PRD-206-list-workflows-assign-cli]]"
  - "[[PRD-210-runner]]"
impacts:
  - tools/prd-harness/workflows/default/workflow.py
  - tools/prd-harness/workflows/default/prompts/role.md
  - tools/prd-harness/workflows/default/prompts/task.md
  - tools/prd-harness/workflows/default/prompts/verify.md
workflow: null
target_version: null
created: 2026-04-07
updated: 2026-04-07
tags:
  - harness
  - workflows
  - default
---

# Default Workflow + Prompts

## Summary

Ship the catchall `default` workflow that runs for any PRD without specialization. Pure data — the workflow.py module composes `BuiltIn`/`AgentTask`/`ShellTask` into a standard SDLC recipe. Also ships the agent prompt files (role, task, verify).

## Requirements

1. `tools/prd-harness/workflows/default/workflow.py` exports a `workflow = Workflow(...)` object
2. Task list: ensure_worktree → set_status(in-progress) → commit → AgentTask(implement) → test → lint → commit → set_status(review) → push_branch → create_pr
3. AgentTask uses `model_from_capability=True` and a tool allowlist covering Read/Edit/Write/Glob/Grep + Bash for cargo/pnpm/just/git-read commands
4. `applies_to=lambda prd, prds: True` and `priority=0` (catchall, lowest priority)
5. Three prompt files in `prompts/`: `role.md`, `task.md`, `verify.md`
6. Prompts reference template placeholders: `{{PRD_ID}}`, `{{PRD_TITLE}}`, `{{PRD_PATH}}`, `{{BRANCH_NAME}}`, `{{WORKTREE_PATH}}`, `{{CHECK_OUTPUT}}` (verify only)

## Technical Approach

**New file**: `tools/prd-harness/workflows/default/workflow.py`

Imports `Workflow`, `BuiltIn`, `AgentTask`, `ShellTask` from `prd_harness.workflow` and composes the task list.

**New files**:
- `workflows/default/prompts/role.md` — "You are implementing a single Pumice PRD..." — sets up agent persona and sentinel contract
- `workflows/default/prompts/task.md` — templated instructions: read the PRD, implement, test, commit, emit sentinel
- `workflows/default/prompts/verify.md` — retry prompt with `{{CHECK_OUTPUT}}` placeholder for failed check output

## Acceptance Criteria

- [ ] AC-1: `workflow.py` exports a `Workflow` named `"default"` with 10+ tasks
- [ ] AC-2: Loader picks it up: `load_workflows(dir)["default"]` returns it
- [ ] AC-3: All three prompt files exist and contain at least one template placeholder
- [ ] AC-4: Workflow has `priority=0` and always-true `applies_to`
- [ ] AC-5: No tests needed (data only); verification happens via loader tests
