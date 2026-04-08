---
id: "PRD-211"
title: "plan + run CLI Subcommands"
kind: task
status: done
priority: high
effort: s
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-206-list-workflows-assign-cli]]"
  - "[[PRD-209-real-builtins]]"
  - "[[PRD-210-runner]]"
blocks: []
impacts:
  - tools/prd-harness/src/prd_harness/cli.py
  - tools/prd-harness/tests/test_cli.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - cli
  - execution
---

# plan + run CLI Subcommands

## Summary

Add `prd plan <PRD-ID>` and `prd run <PRD-ID>` subcommands. `plan` shows the execution plan without touching anything (resolves workflow, composes prompt, lists steps). `run` actually executes the runner against the PRD. `run --execute` is the opt-in for real execution; default is dry-run.

## Requirements

1. `prd plan <PRD-ID>` — read-only, shows:
   - Which workflow the PRD will use (via `assign_workflow`)
   - Branch name and base ref
   - Model that will be used (capability → haiku/sonnet/opus)
   - Composed prompt preview (first ~50 lines)
   - Ordered task list with type (BuiltIn/AgentTask/ShellTask) and kwargs
2. `prd run <PRD-ID> [--execute] [--base REF] [--workflow NAME] [--model NAME]`:
   - Without `--execute`: dry-run (same as `prd plan` essentially)
   - With `--execute`: invoke `runner.run_workflow(...)` for real
   - `--base` overrides base ref (default: current HEAD)
   - `--workflow` overrides assignment
   - `--model` overrides capability→model mapping
3. Both commands fail fast with a clear error if the PRD is not actionable or not runnable (is an epic with children, etc.)
4. `run --execute` prints PR URL on success, status update on failure

## Technical Approach

**Modify**: `tools/prd-harness/src/prd_harness/cli.py`

- Register `cmd_plan` and `cmd_run` subcommands
- Both load PRDs, workflows, assign, then hand off to the runner with `dry_run=True` (plan) or `dry_run=not args.execute` (run)
- Use `graph.is_actionable` + `containment.is_runnable` to gate execution
- Import `runner.run_workflow` and call it
- Pretty-print the result (use rich or just plain text; stick with plain for now)

**Modify**: `tools/prd-harness/tests/test_cli.py`

- Test `prd plan` produces output with no git changes
- Test `prd run` (dry-run) is equivalent to `prd plan`
- Test `prd run --execute` with a mocked runner works end-to-end

## Acceptance Criteria

- [ ] AC-1: `just prd-dev plan PRD-201` prints the execution plan (workflow, tasks, prompt preview)
- [ ] AC-2: `just prd-dev run PRD-201` without `--execute` is a no-op dry-run equivalent to `plan`
- [ ] AC-3: `just prd-dev run PRD-201 --execute` runs the runner
- [ ] AC-4: Errors surface cleanly when PRD is not actionable or not runnable
- [ ] AC-5: `mypy --strict` passes
- [ ] AC-6: `pytest tests/test_cli.py` passes
