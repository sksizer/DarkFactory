---
id: PRD-567
title: "Workflow reliability improvements: auto-recovery, permission hygiene, and containment"
kind: epic
status: draft
priority: high
effort: l
capability: complex
parent:
depends_on: []
blocks:
  - "[[PRD-567.1-ensure-worktree-auto-recovery]]"
  - "[[PRD-567.2-reduce-permission-denial-token-waste]]"
  - "[[PRD-567.3-file-deletion-permissions]]"
  - "[[PRD-567.4-filesystem-containment-hardening]]"
  - "[[PRD-567.5-pre-run-stale-cleanup]]"
  - "[[PRD-567.6-refactor-workflow]]"
  - "[[PRD-567.7-planning-workflow-template-alignment]]"
  - "[[PRD-567.8-structured-failure-context-in-events]]"
impacts:
  - src/darkfactory/builtins/ensure_worktree.py
  - src/darkfactory/invoke.py
  - src/darkfactory/workflows/task/workflow.py
  - src/darkfactory/workflows/planning/workflow.py
  - src/darkfactory/workflows/default/prompts/role.md
  - src/darkfactory/workflows/task/prompts/role.md
  - src/darkfactory/workflows/task/prompts/task.md
  - src/darkfactory/workflows/default/prompts/task.md
  - src/darkfactory/graph_execution.py
  - src/darkfactory/event_log.py
  - src/darkfactory/templates_builtin.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: 2026-04-09
tags:
  - harness
  - reliability
  - permissions
  - containment
---

# Workflow reliability improvements: auto-recovery, permission hygiene, and containment

## Summary

Analysis of 18 event logs and 36 agent transcripts reveals that while individual agent tasks succeed 97% of the time, overall PRD-level completion sits at only 56% due to harness infrastructure failures. The primary causes are stale worktree/branch state blocking re-runs (45% of failures), wasted tokens on permission denials agents should never attempt (~76K tokens per batch), and gaps in filesystem containment and deletion permissions.

This epic addresses all identified reliability issues in a prioritised sequence of tasks.

## Motivation

DarkFactory is being used to orchestrate its own development. As the project moves toward drain-ready-queue execution (PRD-563) and parallel execution (PRD-551), reliability issues that are tolerable in single-PRD interactive runs become blockers for unattended batch execution. A `prd run --all --execute --max-runs 10` overnight run that fails on 45% of PRDs due to stale branch state — not implementation difficulty — is wasted compute and wasted time.

The fixes in this epic are ordered so that each one independently improves reliability, and the highest-impact changes ship first.

## Analysis

### Data sources

- 18 JSONL event files from `.darkfactory/events/`
- 36 transcript logs from `.darkfactory/transcripts/`
- 4 workflow definitions (default, task, planning, extraction)
- Core harness code (runner, invoke, builtins, checks, templates)
- 4 previously documented issues (worktree containment gap, git-add pattern mismatch, PRD-560 failure, hardcoded PRD path)

### Finding 1: Stale worktree state is the dominant failure mode

5 out of 9 PRD-level failures were caused by `ensure_worktree` detecting a local branch whose worktree directory no longer exists and raising `RuntimeError`. The error message tells the user to run `prd cleanup`, but in batch execution there is no user present.

Affected PRDs: PRD-227.4, PRD-227.6 (orphaned branches), PRD-563 (merged PR branch not cleaned up), plus cascade-blocked dependents.

Root cause in `ensure_worktree.py:143-152`: the function checks for existing branches and raises unconditionally if found, even when the associated PR is already merged or closed and auto-recovery would be safe.

### Finding 2: Agents waste tokens on denied git operations

153 "requires approval" errors across 100% of transcripts. Every agent session hits permission denials for `git commit`, despite the role prompt explicitly saying "Do not run git commit." The pattern:

1. Agent tries `git add && git commit` → compound command blocked
2. Agent splits into separate commands
3. Agent tries `git commit` standalone → blocked again
4. Agent gives up

Worst cases: PRD-549.12 (26 denials), PRD-230 (7), PRD-227.5 (7), PRD-549.2 (7). At ~500 tokens per denial cycle, this wastes ~76K tokens per batch.

Two contributing factors:
- The prompt says "do not commit" but doesn't give a concrete example of the blocked command or explain why retrying is pointless
- `git commit` is not in the `--allowed-tools` list, but it's also not explicitly in `--disallowed-tools` — so Claude Code's permission system handles it as "requires approval" rather than instant rejection

### Finding 3: File deletion is blocked even when the workflow allows it

PRD-549.12 (delete old `tests/test_builtins.py`) is the only task-level failure in the entire dataset. The task workflow includes `Bash(git rm:*)` in its tool allowlist, but the agent was still blocked from deleting the file.

The agent likely attempted direct file deletion (`rm` or an `os.remove`-style approach) rather than `git rm`, or Claude Code's sandbox has an additional deletion guard beyond the `--allowed-tools` flag.

### Finding 4: Filesystem containment has gaps

The current containment (`--disallowed-tools "Edit(../)"`) uses relative-path patterns. Agents can escape by using absolute paths: `Write("/Users/.../DarkFactory/.darkfactory/prds/...")` bypasses the `../` check. This was observed during PRD-560 when a planning agent in a worktree wrote child PRDs to the main repo.

### Finding 5: Planning workflow drifts from template invariants

The planning workflow (`planning/workflow.py`) builds its full task list manually instead of using `PRD_IMPLEMENTATION_TEMPLATE.compose()`. This means it can drift from the SDLC invariants the template enforces (commit_events ordering, lint_attribution placement, etc.).

## Requirements

### R1: Auto-recovery in ensure_worktree

When `ensure_worktree` detects `branch exists + worktree missing`, check the PR state via `gh`. If the PR is merged or closed, automatically delete the local branch and proceed with fresh worktree creation instead of raising. Only raise if the PR is still open or unknown.

### R2: Reduce permission denial token waste

Two changes:
1. Add `git commit`, `git push`, and `gh pr` to the `--disallowed-tools` list in `invoke.py` so denials are instant (no round-trip through Claude Code's approval system).
2. Harden the role/task prompts to include concrete examples of blocked commands and explicit instruction not to retry denied operations.

### R3: Fix file deletion permissions

Ensure the task workflow's `Bash(git rm:*)` permission actually works, and add `Bash(rm:*)` for direct file deletion. Verify the fix by confirming the permission pattern matches real-world deletion commands.

### R4: Harden filesystem containment

Replace relative-path `--disallowed-tools "Edit(../)"` with patterns that also block absolute-path escapes. Consider blocking all absolute paths to `/Users/` and relying on relative paths within the worktree, or computing the repo root at invocation time and blocking writes to it specifically.

### R5: Pre-run stale cleanup in batch execution

Before the DAG execution loop begins, automatically find and clean stale worktrees (merged/closed PRs) using the existing `find_stale_worktrees` + `is_safe_to_remove` functions from `checks.py`. This prevents stale state from accumulating across batch runs.

### R6: Refactor/deletion workflow

Create a `refactor` workflow that matches PRDs tagged `cleanup` or `refactor` (or with "delete"/"remove" in the title). Grant wider permissions than the standard task workflow: `Bash(rm:*)`, `Bash(mv:*)`, `Bash(find:*)` in addition to `Bash(git rm:*)`.

### R7: Planning workflow template alignment

Refactor the planning workflow to use a `WorkflowTemplate` (either the existing `PRD_IMPLEMENTATION_TEMPLATE` or a new `PLANNING_TEMPLATE`) so its open/close sequences stay in sync with SDLC invariants.

### R8: Structured failure context in event logs

When a task fails, include stderr and failure detail in the `task_finish` event. Currently failures like the PRD-227.3 `gh pr create` failure log only `exit status 1` with no diagnostic detail.

## Decomposition plan

| Child | Title | Effort | Priority | Depends on |
|-------|-------|--------|----------|------------|
| PRD-567.1 | ensure_worktree auto-recovery for merged/closed PRs | s | high | — |
| PRD-567.2 | Reduce permission denial token waste (disallow + prompt) | xs | high | — |
| PRD-567.3 | Fix file deletion permissions in task workflow | xs | high | — |
| PRD-567.4 | Filesystem containment hardening (absolute path blocks) | m | high | — |
| PRD-567.5 | Pre-run stale cleanup in graph execution | s | medium | 567.1 |
| PRD-567.6 | Refactor/deletion workflow | s | medium | 567.3 |
| PRD-567.7 | Planning workflow template alignment | s | medium | — |
| PRD-567.8 | Structured failure context in event logs | xs | low | — |

567.1 through 567.4 are independent and can execute in parallel.
567.5 depends on 567.1 (reuses the auto-recovery logic).
567.6 depends on 567.3 (needs validated deletion permissions).
567.7 and 567.8 are independent of everything else.

## Acceptance criteria

- [ ] AC-1: `prd run --all --execute` on a repo with stale branches from merged PRs succeeds without manual `prd cleanup` intervention.
- [ ] AC-2: Agent transcripts show zero `git commit` denial cycles (denials are instant via `--disallowed-tools`).
- [ ] AC-3: A task PRD requiring file deletion (like PRD-549.12) completes successfully.
- [ ] AC-4: An agent running in a worktree cannot write to the main repo using absolute paths.
- [ ] AC-5: Batch execution automatically cleans stale worktrees before starting the DAG loop.
- [ ] AC-6: PRDs tagged `refactor` or `cleanup` are assigned the refactor workflow with deletion permissions.
- [ ] AC-7: The planning workflow's open/close sequences are generated from a `WorkflowTemplate`, not manually listed.
- [ ] AC-8: Failed task events include stderr and structured failure detail, not just exit codes.

## References

- [[PRD-220-graph-execution]] — the execution loop this improves
- [[PRD-224-harness-invariants-honest-state]] — invariants this reinforces
- [[PRD-227-workflow-templates]] — the template system 567.7 aligns with
- [[PRD-549-split-builtins-into-package-with-colocated-tests]] — the epic whose cleanup task (549.12) exposed the deletion permission gap
- [[PRD-551-parallel-graph-execution]] — parallel execution benefits from higher single-run reliability
- [[PRD-563-drain-ready-queue-execution-mode]] — batch mode that makes reliability critical
