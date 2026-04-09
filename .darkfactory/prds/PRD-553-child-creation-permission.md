---
id: PRD-553
title: Make "create child PRDs" an explicit task-level permission
kind: feature
status: draft
priority: medium
effort: s
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-220-graph-execution]]"
impacts:
  - src/darkfactory/workflow.py
  - src/darkfactory/runner.py
  - workflows/planning/workflow.py
  - tests/test_workflow_permissions.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - permissions
  - workflows
  - safety
---

# Make "create child PRDs" an explicit task-level permission

## Summary

Today the planning workflow can write new PRD files under `prds/` because its tool allowlist happens to include `Write` scoped to that directory. That's implicit and invisible. This PRD makes "this task is allowed to generate child PRDs" an **explicit** permission that a workflow/task must declare, and enforces it both at prompt-composition time (the agent is told what it can/can't do) and at post-run validation time (new PRD files from a task without the permission are a failure).

## Motivation

Graph execution (PRD-220) re-loads the PRD set between runs to pick up newly-created children. That's powerful — and unsafe if *any* task can silently grow the DAG. A bugfix task that accidentally generates three new PRDs is a bad day.

Explicit permission gives us:

- **Predictability** — reading a workflow definition tells you whether it can grow the DAG.
- **Safety** — a task without the permission that writes a new PRD file fails its run (and the file is reverted or quarantined).
- **Observability** — graph executor logs can tag "this iteration grew the DAG via PRD-X" because we know which runs were entitled to do that.
- **`--max-runs` honesty** — PRD-220 counts introduced children against `--max-runs`. If arbitrary tasks can introduce children, the budget is unbounded.

## Requirements

1. New workflow-task field: `can_create_prds: bool` (default `false`).
2. Workflow loader validates: if `can_create_prds=true`, the task's tool allowlist must include `Write` for `prds/**`. If `can_create_prds=false`, `Write` for `prds/**` is stripped from the allowlist before prompt composition.
3. Post-run validator: after a task completes, diff the `prds/` directory in its worktree. If new PRD files exist and the task didn't have `can_create_prds=true`, the run fails and the files are reverted.
4. Planning workflow (`workflows/planning/workflow.py`) is updated to set `can_create_prds=true` on its decomposition task. Every other existing workflow stays implicitly false.
5. PRD-220's graph executor reads this field when deciding whether to re-load PRDs after a run — no need to re-scan if the task couldn't have created anything.

## Open questions

- [ ] Symmetric permissions for *modifying* existing PRDs? Probably yes as a follow-up — `can_modify_prds` — but out of scope here.
- [ ] Should the permission be per-task or per-workflow? Per-task is more granular and matches how tool allowlists already work.
- [ ] Error UX when violation happens mid-run: fail loud with the offending file path, or quarantine the file somewhere and mark the PRD `review`?

## References

- [[PRD-220-graph-execution]] — consumer; relies on this for `--max-runs` honesty.
- `workflows/planning/workflow.py` — the one legitimate creator of child PRDs today.
