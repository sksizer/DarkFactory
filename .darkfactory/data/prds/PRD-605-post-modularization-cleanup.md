---
id: "PRD-605"
title: "Post-modularization code cleanup"
kind: task
status: blocked
priority: low
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - "python/darkfactory/cli/run.py"
  - "python/darkfactory/cli/assign_cmd.py"
workflow: null
target_version: null
created: '2026-04-09'
updated: '2026-04-09'
tags:
  - harness
  - quality
---

# Post-modularization code cleanup

## Problem

During the PRD-556.x modularization reviews, several pre-existing issues were identified but correctly deferred from move PRs (which require behavior-identical moves). Now that the moves are landing, these should be cleaned up.

### From PR #141 (run.py)
1. `events` list in `cmd_run` and graph execution accumulates `RunEvent` objects but is never consumed. Unbounded memory growth proportional to run size.

### From PR #137 (assign_cmd.py)
2. Comment says explicit assignments are marked with `*`, but code outputs "explicit" in Source column. Comment/behavior mismatch.
3. Human output uses truthiness (`if prds[prd_id].workflow`) while JSON uses `is not None` check. Can disagree for falsy-but-not-None values.

## Requirements

1. Either remove the `events` list from `cmd_run`/graph execution, or connect it to a post-run summary.
2. Update the comment in `assign_cmd.py` to match actual output behavior.
3. Standardize the workflow check to `is not None` in both human and JSON output paths.

## Acceptance criteria

- [ ] No unbounded `events` accumulation in run.py (removed or consumed)
- [ ] assign_cmd.py comment matches actual output format
- [ ] Consistent `is not None` check for workflow in assign_cmd.py

## Assessment (2026-04-11)

- **Value**: 3/5 — the unbounded `events` accumulation in `cmd_run`
  is a real (if slow-growing) memory leak; the `assign_cmd.py`
  inconsistencies are comment/behavior drift. Both are polish, not
  correctness, but they're cheap to fix.
- **Effort**: xs — three focused edits in two files.
- **Current state**: greenfield on the fixes. Blocked status should
  unblock immediately — PRD-556 is essentially done (see its
  assessment) and nothing else holds this up.
- **Gaps to fully implement**:
  - Remove the unused `events` list from `cmd_run` in `cli/run.py`
    (or wire it into a post-run summary if the intent was to emit
    a batch report).
  - Fix the comment in `cli/assign_cmd.py` to match the "explicit"
    column output.
  - Standardize to `is not None` for the workflow truthiness check.
- **Recommendation**: do-now — unblock, pair with PRD-556.18 as the
  modularization close-out PR. Half-hour of work including tests.
