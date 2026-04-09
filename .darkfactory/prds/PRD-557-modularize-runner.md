---
id: PRD-557
title: Split src/darkfactory/runner.py into per-dispatcher modules with colocated tests
kind: epic
status: draft
priority: low
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-549-builtins-package-split]]"
blocks: []
impacts:
  - src/darkfactory/runner.py
  - tests/test_runner.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - refactor
  - tests
  - organization
  - runner
---

# Split `src/darkfactory/runner.py` into per-dispatcher modules

## Summary

`src/darkfactory/runner.py` is 465 lines and holds the workflow execution engine — entry point, task dispatch, three per-task-kind runners (builtin, agent, shell), the retry-on-failure path, worktree-lock bookkeeping, and the result dataclasses. It's moderately sized, not yet urgent, but following it is a natural sibling refactor to PRD-549 and PRD-556.

Apply the same package-of-submodules convention. Lower priority than PRD-556 (CLI is bigger and more frequently touched), but worth capturing so the pattern is consistent across all large modules.

## Motivation

- **Dispatch-kind coupling.** Each of `_run_builtin`, `_run_agent`, and `_run_shell` is 50-100 lines of focused logic for a single task type. Keeping them in one file means a change to agent retry logic shares diff space with shell env handling and builtin arg formatting.
- **Retry path complexity.** The retry-agent path is the most intricate code in the file and the hardest to isolate for testing. A dedicated module makes the retry machinery testable in isolation.
- **Growth trajectory.** PRD-552 (merge-upstream task) will likely add a new task-kind dispatcher. Landing it in a single-file runner adds more surface area to an already-busy file. Splitting first makes 552's landing smaller.
- **Result types and context plumbing** deserve their own home.

## Target layout

```
src/darkfactory/
├── runner/
│   ├── __init__.py              # re-exports run_workflow, RunResult, TaskStep
│   ├── _shared.py               # _task_name, _task_kind, _release_worktree_lock, _pick_model
│   ├── _shared_test.py
│   ├── result.py                # RunResult, TaskStep dataclasses
│   ├── loop.py                  # run_workflow — the top-level dispatch loop
│   ├── loop_test.py
│   ├── dispatch.py              # _dispatch — the type-routing function
│   ├── dispatch_test.py
│   ├── builtin.py               # _run_builtin
│   ├── builtin_test.py
│   ├── agent.py                 # _run_agent + transcript dump
│   ├── agent_test.py
│   ├── shell.py                 # _run_shell + _run_shell_once + retry-agent path
│   └── shell_test.py
```

Public API preservation: `from darkfactory.runner import run_workflow, RunResult` must keep working.

## Decomposition DAG

- **A** — pytest/colocated-test scaffolding (inherited from PRD-549.1).
- **B** — scaffold the `runner/` package, move `result.py`, `_shared.py`, and a stub `loop.py` that re-imports from the old monolith.
- **C1** — move `_run_builtin` into `builtin.py` + colocated test.
- **C2** — move `_run_agent` into `agent.py` + colocated test.
- **C3** — move `_run_shell` + retry-agent path into `shell.py` + colocated test.
- **C4** — move `run_workflow` + `_dispatch` into `loop.py` + `dispatch.py` + colocated tests.
- **D** — delete the old monolith, verify `runner/` is the single source.

Smaller fan-out than PRD-549 (4 real children instead of 9), less parallel opportunity but still a clean stress test.

## Acceptance criteria

- [ ] AC-1: `src/darkfactory/runner/` exists as a package, `__init__.py` re-exports `run_workflow`, `RunResult`, `TaskStep`.
- [ ] AC-2: Each of builtin/agent/shell dispatchers lives in its own submodule with colocated `*_test.py`.
- [ ] AC-3: The retry-agent path has dedicated unit tests at `shell_test.py` — the hardest-to-isolate logic gets the most focused coverage.
- [ ] AC-4: All existing tests pass. No behavior changes.
- [ ] AC-5: `just test && just lint && just typecheck && just format-check` clean at every child PRD merge.
- [ ] AC-6: Public API unchanged.

## Open questions

- [ ] Does `ExecutionContext` (currently in `workflow.py`) move into `runner/`? It's tightly coupled to runner but also used by `builtins.py`. Recommend: keep in `workflow.py` for now, revisit if it becomes awkward.
- [ ] Should `_pick_model` live in `runner/_shared.py` or in `invoke.py` alongside `capability_to_model`? Probably `invoke.py` — they're related. Out of scope for this PRD; capture as a follow-up cleanup.
- [ ] PRD-552 interaction. If PRD-552 introduces a new dispatcher (`_run_merge_upstream` or similar), it should land as a new submodule under this package. Ordering: 557 first, then 552 can follow the pattern. Reverse order works too, just noisier.

## References

- [[PRD-549-builtins-package-split]] — the template this epic follows.
- [[PRD-556-modularize-cli]] — sibling modularization of the other large module.
- [[PRD-552-merge-upstream-task]] — likely future dispatcher consumer.
- Current `src/darkfactory/runner.py` — 465 lines.
