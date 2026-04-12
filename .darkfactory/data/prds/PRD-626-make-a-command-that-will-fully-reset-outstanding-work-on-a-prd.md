---
id: PRD-626
title: Make a command that will fully reset outstanding work on a PRD
kind: task
status: review
priority: medium
effort: h
capability: moderate
parent:
depends_on:
  - "[[PRD-622-data-model-refactor]]"
blocks: []
impacts: []
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: '2026-04-11'
tags: []
---

# Make a command that will fully reset outstanding work on a PRD

## Summary

Add a `prd reset PRD-XXX` command that fully undoes all outstanding work on a PRD — closing PRs, deleting worktrees and branches, clearing rework guard state — and returns the PRD to `ready` status so it can be cleanly re-run.

## Motivation

When an agent run produces garbage output, requirements change mid-flight, or a rework loop gets stuck, there is no clean way to start over. The existing `prd cleanup` command only handles worktrees for completed (merged) PRDs. Users are left manually closing PRs, deleting branches, removing worktrees, and editing frontmatter — error-prone and tedious. A single reset command eliminates this friction and makes iteration on PRDs fast and safe.

## Requirements

### Functional

1. `prd reset PRD-XXX` collects all outstanding artifacts for the given PRD: worktree directory, lock file, local branch, remote branch, open PR(s), rework guard entry, and current status.
2. Default mode is **dry-run**: display the artifact summary and exit. `--execute` flag performs the actual reset. This follows the `prd run`/`prd rework` convention.
3. In `--execute` mode, display the artifact summary and prompt for Y/n confirmation before taking any destructive action. `--yes` flag skips the confirmation prompt (for scripting/automation).
4. **Status guard** — behaviour depends on current PRD status:
   - `in-progress`, `review`, `blocked`: proceed normally (active/stuck states with potential artifacts).
   - `draft`, `ready`: warn "no workflow has run"; still probe for orphaned artifacts from partial failures but do not change the status field.
   - `done`, `cancelled`, `superseded`, `archived`: reject with error — these are terminal states (resetting them is semantically wrong).
5. **Concurrency check** — before any mutation, attempt to acquire the `FileLock` at `.worktrees/{prd_id}.lock` with `timeout=0` (non-blocking), matching `ensure_worktree.py`. If the lock is held, abort with: *"Cannot reset {prd_id}: a workflow is currently running (lock held at {path}). Stop the running process first."*
6. On confirmation, execute cleanup in dependency order:
   a. Close **all** open PRs for the branch on GitHub, each with a comment: "Closed by `prd reset`." Log each closed PR number. <!-- Close all, not just first — orphaned open PRs are worse than closing an unexpected extra. -->
   b. Remove the worktree via `git worktree remove --force`, then `git worktree prune` to clean any stale metadata. <!-- Raw rm -rf leaves stale .git/worktrees/ entries — never use it. -->
   c. Release and remove the worktree lock file (`.worktrees/{prd_id}.lock`). <!-- Lock must be acquired in FR-5 before reaching this step. -->
   d. Delete all local branches matching `prd/{prd_id}-*` (glob match, no slug reconstruction needed).
   e. Delete all remote branches matching `origin/prd/{prd_id}-*`.
   f. Remove the PRD's entry from `.darkfactory/state/rework-guard.json` via `ReworkGuard.reset()`.
   g. Reset the PRD's status to `ready` by loading the PRD via `model.load_one(data_dir, prd_id)` and calling `model.set_status(prd, "ready")`. The model handles path resolution, `updated` timestamp, and persistence internally.
   h. Emit a `cli/prd_reset` event to the event log containing `prd_id`, lists of artifacts cleaned and artifacts skipped. (Execute mode only — dry-run must not emit events.)
7. Each step (6a–6g) is best-effort and non-fatal — if a PR doesn't exist or a branch is already gone, skip that step and continue. Report what was done and what was skipped. Step 6h (event emission) must always execute when in `--execute` mode.
8. Leave the `workflow` assignment in frontmatter intact.
9. Single-PRD only — no batch/`--all` mode.

### Non-Functional

1. Extract shared worktree/branch discovery and removal functions into `worktree_utils.py` (which already exists). Specifically: the `StaleWorktree`-wrapping discovery from `cleanup.py`, `_find_orphaned_branch`, and `_remove_worktree` should move to `worktree_utils` so both `cleanup` and `reset` import from the same module.
2. Fail loudly if the PRD ID doesn't exist (see FR-4 for per-status behaviour).
3. Operation should be idempotent — running `prd reset` twice on the same PRD should succeed (second run finds nothing to clean and reports that).

## Technical Approach

- New CLI subcommand in `src/darkfactory/cli/reset.py`, registered in `_parser.py`.
- **Shared utilities refactor**: before implementing, extract `_find_worktree_for_prd` (the `StaleWorktree`-wrapping variant), `_find_orphaned_branch`, and `_remove_worktree` from `cleanup.py` into `worktree_utils.py`. Update `cleanup.py` to import from there. Then `reset.py` imports the same functions.
- **Discovery phase**: probe for each artifact type — `find_worktree_for_prd()`, `gh pr list --state open --head {branch}`, `git branch --list prd/{prd_id}-*` (glob match, no slug needed), `ReworkGuard.is_blocked()` / entry existence, frontmatter status read via `model.load_one(data_dir, prd_id)`. Collect results into a summary dataclass.
- **Concurrency gate**: acquire `FileLock` at `.worktrees/{prd_id}.lock` (non-blocking) before entering execution phase. Abort if held.
- **Execution phase**: ordered teardown per FR-6, using `subprocess` for git/gh commands, `ReworkGuard.reset()` for guard state, and `model.set_status(prd, "ready")` for frontmatter (model handles path resolution and persistence).
- **Event emission**: write a `cli/prd_reset` event via `EventWriter` with the artifact cleanup results. This runs outside an `ExecutionContext` — instantiate the writer directly as `reconcile.py` does.
- Rich output for the summary table and confirmation prompt.

## Acceptance Criteria

- [ ] AC-1: `prd reset PRD-XXX` (no flags) prints the artifact summary and exits without modifying anything (dry-run default).
- [ ] AC-2: `prd reset PRD-XXX --execute` on a PRD with worktree + open PR + remote branch resets all artifacts and sets status to `ready`.
- [ ] AC-3: Running `prd reset --execute` on a PRD with no outstanding work reports "nothing to reset" and exits cleanly.
- [ ] AC-4: `--execute --yes` skips confirmation and completes without interactive prompt.
- [ ] AC-5: Partial artifact state (e.g., worktree exists but no PR) is handled gracefully — present artifacts are cleaned, missing ones are skipped.
- [ ] AC-6: All open PRs for the branch are closed, each with a comment attributing the closure to `prd reset`.
- [ ] AC-7: `workflow` field in frontmatter is preserved after reset.
- [ ] AC-8: Rework guard entry for the PRD is removed after reset.
- [ ] AC-9: `updated` frontmatter field is set to today's date after reset.
- [ ] AC-10: A `cli/prd_reset` event is emitted to the event log with artifact cleanup details.
- [ ] AC-11: Reset on a `done`/`cancelled`/`superseded`/`archived` PRD fails with a clear error.
- [ ] AC-12: Reset while a workflow is actively running (lock held) fails with a clear error.
- [ ] AC-13: Shared worktree utilities extracted from `cleanup.py` into `worktree_utils.py`; `cleanup.py` still passes its existing tests.

## Open Questions

- RESOLVED: Target status after reset → `ready`
- RESOLVED: Confirmation model → dry-run by default, `--execute` to act, `--yes` to skip prompt
- RESOLVED: Batch mode → not in scope, single PRD only
- RESOLVED: Workflow assignment → preserved, not cleared
- RESOLVED: Terminal status handling → `done`/`cancelled`/`superseded`/`archived` rejected with error (matches `TERMINAL_STATUSES` in model)
- RESOLVED: Source-repo frontmatter write → use `model.load_one()` + `model.set_status()` — model owns path resolution and persistence
- RESOLVED: Worktree removal → `git worktree remove --force` + `prune`, never raw `rm -rf`
- RESOLVED: Concurrent execution → acquire `FileLock` non-blocking, abort if held
- RESOLVED: Multiple open PRs → close all, log each
- RESOLVED: Event emission → required, emit `cli/prd_reset` with artifact details

## References

- Existing `prd cleanup` command: `src/darkfactory/cli/cleanup.py`
- Rework guard state: `src/darkfactory/builtins/rework_guard.py`
- Worktree management: `src/darkfactory/builtins/ensure_worktree.py`

