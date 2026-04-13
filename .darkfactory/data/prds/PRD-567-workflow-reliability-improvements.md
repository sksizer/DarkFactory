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
  - "[[PRD-567.1-worktree-lifecycle-resilience]]"
  - "[[PRD-567.2-agent-permission-hygiene]]"
  - "[[PRD-567.3-file-operation-permissions]]"
  - "[[PRD-567.4-filesystem-containment-hardening]]"
  - "[[PRD-567.5-planning-workflow-template-alignment]]"
  - "[[PRD-567.6-structured-failure-context-in-events]]"
impacts: []
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
| PRD-567.1 | Worktree lifecycle resilience: auto-recovery and pre-run cleanup | m | high | — |
| PRD-567.2 | Agent permission hygiene: eliminate denial waste and harden prompts | s | high | — |
| PRD-567.3 | File operation permissions and workflow specialization | s | high | — |
| PRD-567.4 | Filesystem containment hardening: block absolute-path escapes | m | high | — |
| PRD-567.5 | Planning workflow template alignment | s | medium | — |
| PRD-567.6 | Structured failure context in event logs | xs | low | — |

567.1 through 567.4 are independent and can execute in parallel.
567.5 and 567.6 are independent of everything else.

Note: PRD-567.1–567.4 are further decomposed into sub-tasks (e.g. PRD-567.1.1–567.1.3).

## Acceptance criteria

- [ ] AC-1: `prd run --all --execute` on a repo with stale branches from merged PRs succeeds without manual `prd cleanup` intervention.
- [ ] AC-2: Agent transcripts show zero `git commit` denial cycles (denials are instant via `--disallowed-tools`).
- [ ] AC-3: A task PRD requiring file deletion (like PRD-549.12) completes successfully.
- [ ] AC-4: An agent running in a worktree cannot write to the main repo using absolute paths.
- [ ] AC-5: Batch execution automatically cleans stale worktrees before starting the DAG loop.
- [ ] AC-6: PRDs tagged `refactor` or `cleanup` are assigned the refactor workflow with deletion permissions.
- [ ] AC-7: The planning workflow's open/close sequences are generated from a `WorkflowTemplate`, not manually listed.
- [ ] AC-8: Failed task events include stderr and structured failure detail, not just exit codes.

## Impacted files (informational)

These are the expected files to be modified across child tasks:

- `python/darkfactory/builtins/ensure_worktree.py`
- `python/darkfactory/invoke.py`
- `python/darkfactory/workflows/task/workflow.py`
- `python/darkfactory/workflows/planning/workflow.py`
- `python/darkfactory/workflows/default/prompts/role.md`
- `python/darkfactory/workflows/task/prompts/role.md`
- `python/darkfactory/workflows/task/prompts/task.md`
- `python/darkfactory/workflows/default/prompts/task.md`
- `python/darkfactory/graph_execution.py`
- `python/darkfactory/event_log.py`
- `python/darkfactory/templates_builtin.py`

## References

- [[PRD-220-graph-execution]] — the execution loop this improves
- [[PRD-224-harness-invariants-honest-state]] — invariants this reinforces
- [[PRD-227-workflow-templates]] — the template system 567.7 aligns with
- [[PRD-549-split-builtins-into-package-with-colocated-tests]] — the epic whose cleanup task (549.12) exposed the deletion permission gap
- [[PRD-551-parallel-graph-execution]] — parallel execution benefits from higher single-run reliability
- [[PRD-563-drain-ready-queue-execution-mode]] — batch mode that makes reliability critical

## Assessment (2026-04-11)

- **Value**: 5/5 — this is the single most-felt pain cluster. The data
  the epic cites is real: 45% of PRD-level failures came from stale
  worktree state and ~76K tokens per batch wasted on permission denials.
  Every batch run benefits.
- **Effort**: l for the full epic. The biggest chunks are 567.1
  (auto-recovery + pre-run cleanup) and 567.4 (containment hardening).
  567.2 and 567.3 are s; 567.5 and 567.6 are xs–s.
- **Current state**: greenfield across all sub-features. None of the
  six sub-epics have any code landed. State survey confirms:
  - `ensure_worktree.py` still raises on merged-PR stale branches.
  - `invoke.py` does not have `--disallowed-tools` for `git commit`.
  - `task/workflow.py` permissions list is unchanged.
  - `event_log.py` emits only exit codes, not stderr.
  - Planning workflow is still a flat task list, not a template.
- **Gaps to fully implement**: see each sub-epic. The critical path is
  567.1 → 567.2 → 567.3 (in that order of impact).
- **Recommendation**: do-next — split into two PRs. The first covers
  567.1 (auto-recovery + pre-run cleanup) + 567.2 (permission hygiene)
  as a single "batch reliability" PR, since both fix incidents that
  every batch run hits. The second covers 567.3 (deletion permissions)
  + 567.4 (containment) for correctness. 567.5 and 567.6 are opportunistic
  pairings with whichever PR touches the planning workflow or event log.
