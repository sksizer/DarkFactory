---
id: PRD-614
title: Reconcile command errors because of hard coded branch name
kind: bug
status: done
priority: critical
effort: s
capability: moderate
parent: null
depends_on: []
blocks: []
impacts: []
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-10'
updated: '2026-04-10'
tags: []
---

# Reconcile command errors because of hard coded branch name

## Summary

`prd reconcile --execute` crashes with a `CalledProcessError` when the hardcoded branch `prd/reconcile-status` already exists on the remote from a prior run. The command deletes the stale local branch but leaves the remote branch untouched, so the push is rejected as non-fast-forward.

## Motivation

Every second reconcile run fails unconditionally because the stale remote branch blocks the push. The user must manually delete `origin/prd/reconcile-status` between runs, which defeats the automation. Since reconcile is designed to be run repeatedly (it's idempotent on the PRD files themselves), the branch lifecycle must also be handled idempotently.

## Requirements

### Functional

1. `prd reconcile --execute` must succeed on consecutive runs without manual cleanup of any remote branch.
2. Each reconcile run must use a unique branch name so it never collides with a stale remote from a prior run.
3. The branch name must be derived from the current date so it is stable within a day (idempotent retries on the same day reuse the same branch) but unique across days.

### Non-Functional

1. No change to the PR creation flow, commit message, or dry-run behaviour.

## Technical Approach

In `_create_reconcile_pr` (`src/darkfactory/cli/reconcile.py`), replace the hardcoded branch name with one that includes today's date:

```python
from datetime import date

branch = f"prd/reconcile-status-{date.today().strftime('%Y%m%d')}"
```

Example: `prd/reconcile-status-20260410`. The existing local-branch teardown (`git branch -D`, fire-and-forget) already handles same-day retries cleanly. The remote branch from a previous day is simply a different name and never conflicts.

Affected file: `src/darkfactory/cli/reconcile.py`, function `_create_reconcile_pr` (~line 123).

## Acceptance Criteria

- [ ] AC-1: Running `prd reconcile --execute` twice on the same day succeeds on both runs without any manual git intervention.
- [ ] AC-2: The branch pushed to origin is named `prd/reconcile-status-YYYYMMDD` matching today's date.
- [ ] AC-3: All existing tests pass.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- RESOLVED: Timestamp vs. delete-then-push — timestamp chosen because it avoids mutating remote state and leaves a useful audit trail of past reconcile PRs in the branch list.

## References

- `src/darkfactory/cli/reconcile.py`, `_create_reconcile_pr` (line ~118)
- Error reproduced on 2026-04-10 after PR #147 left a stale `prd/reconcile-status` remote branch
