---
id: "PRD-206"
title: "list-workflows + assign CLI Subcommands"
kind: task
status: ready
priority: high
effort: s
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-203-workflow-loader]]"
  - "[[PRD-204-assignment-logic]]"
  - "[[PRD-205-default-workflow]]"
blocks:
  - "[[PRD-211-plan-run-cli]]"
impacts:
  - tools/prd-harness/src/prd_harness/cli.py
  - tools/prd-harness/tests/test_cli.py
workflow: null
target_version: null
created: 2026-04-07
updated: 2026-04-07
tags:
  - harness
  - cli
---

# list-workflows + assign CLI Subcommands

## Summary

Add `prd list-workflows` and `prd assign` subcommands to the harness CLI. Both read-only (no mutations unless `--write` is passed to assign). Lets us dogfood the loader and assignment logic against real PRDs.

## Requirements

1. `prd list-workflows` — print each loaded workflow with name, priority, description; JSON mode via `--json`
2. `prd assign [--write]` — compute the chosen workflow for every PRD; print a table; optionally persist the resolved workflow name into each PRD's frontmatter
3. Workflows loaded from `tools/prd-harness/workflows/` by default; overridable via `--workflows-dir`
4. Both commands respect the global `--prd-dir` flag
5. `--write` mode only touches PRDs where `prd.workflow` is currently `None` (idempotent for re-runs)

## Technical Approach

**Modify**: `tools/prd-harness/src/prd_harness/cli.py`

- Add `--workflows-dir` global flag (default: `tools/prd-harness/workflows`)
- Register `cmd_list_workflows` and `cmd_assign` subcommands
- Import `load_workflows` and `assign_workflow` from the new modules
- For `--write` mode, use `prd.set_status`-style frontmatter rewriter (or add a new helper `set_workflow` in `prd.py` — simpler to add now than generalize later)

**Possibly new helper in `prd.py`**: `set_workflow(prd, workflow_name)` — same round-trip as `set_status` but targets the `workflow` field.

**Modify**: `tools/prd-harness/tests/test_cli.py` (or new file if nonexistent) — verify subcommands work against fixture PRDs + a fixture workflow directory.

## Acceptance Criteria

- [ ] AC-1: `just prd-dev list-workflows` shows the `default` workflow
- [ ] AC-2: `just prd-dev assign` prints each dev-PRD with "→ default"
- [ ] AC-3: `--json` output is valid JSON
- [ ] AC-4: `assign --write` persists the workflow field to frontmatter and is idempotent
- [ ] AC-5: `mypy --strict` passes
- [ ] AC-6: `pytest tests/test_cli.py` passes
