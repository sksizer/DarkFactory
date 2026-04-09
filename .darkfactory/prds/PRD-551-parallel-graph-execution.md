---
id: PRD-551
title: Parallel execution of independent PRDs during graph traversal
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-220-graph-execution]]"
  - "[[PRD-546-impact-declaration-drift-detection]]"
blocks: []
impacts:
  - src/darkfactory/graph_execution.py
  - src/darkfactory/runner.py
  - src/darkfactory/cli.py
  - tests/test_graph_execution_parallel.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - execution
  - dag
  - parallel
---

# Parallel execution of independent PRDs during graph traversal

## Summary

PRD-220 ships sequential graph execution. This PRD adds opt-in parallel execution: when multiple PRDs are simultaneously ready and their `impacts:` don't overlap, run them in parallel worktrees.

## Motivation

The clearest value of DarkFactory is fanning out independent work. Epics like PRD-549 (nine parallel builtin modules) are explicitly designed as DAG stress tests and get no speedup under sequential execution. Sequential is the right first landing; parallel is where the harness earns its keep.

## Requirements

1. `--parallel` flag on `prd run`. Without it, traversal stays sequential (PRD-220 behavior).
2. `--parallel-jobs N` caps concurrency (default: `cpu_count() // 2`).
3. At each scheduling point, group currently-ready PRDs by `impacts_overlap()` (from `impacts.py`). PRDs in the same overlap group serialize; different groups run concurrently up to the jobs cap.
4. Each concurrent leaf gets its own worktree. Existing `ensure_worktree` builtin already scopes locks per PRD id, so N leaves = N locks — no new locking needed as long as each leaf owns a distinct id.
5. PRDs are re-loaded *between batches*, not mid-batch. A planning workflow that finishes inside a batch has its new children picked up on the next iteration.
6. Failure of one parallel job does not cancel its siblings already running; results are collected and the branch-pruning logic from PRD-220 applies once the batch completes.
7. JSON event stream gains a `batch_id` field so consumers can correlate concurrent events.
8. Dry-run under `--parallel` prints the batch groupings: which PRDs would run together, which would serialize, and why (shared impact files).

## Technical approach

- `pick_batch(ready, prds, repo_root, max_jobs)` — pure function. Build overlap graph over `ready`, greedy-color to get independent set, truncate to `max_jobs`.
- Executor uses `concurrent.futures.ThreadPoolExecutor` (each job spawns subprocesses for agent/shell tasks, so threads are fine — the GIL is not the bottleneck).
- Structured logging must be batch-id-tagged to keep concurrent output readable.

## Open questions

- [ ] How does PRD-546's drift detection interact with parallel runs? If job A finishes and touches files that job B (still running) declared as impacts, do we fail B or let it finish? Recommendation: let it finish, flag via PRD-550 mechanism post-hoc.
- [ ] Should parallel mode default to true once stable? Probably not — keeping opt-in matches `just` and `make -j` conventions.
- [ ] Stacked branches + parallel: if jobs A and B both depend on C, they both base on C — no conflict. But A and B landing in parallel then merging to main sequentially is the normal PR flow. Confirm no special handling needed.

## References

- [[PRD-220-graph-execution]] — the sequential foundation.
- [[PRD-546-impact-declaration-drift-detection]] — same file-set computation.
- [[PRD-549-builtins-package-split]] — the intended first real stress test.
