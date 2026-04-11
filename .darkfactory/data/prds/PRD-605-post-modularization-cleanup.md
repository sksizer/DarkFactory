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
  - "src/darkfactory/cli/run.py"
  - "src/darkfactory/cli/assign_cmd.py"
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
