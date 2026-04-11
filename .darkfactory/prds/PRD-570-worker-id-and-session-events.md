---
id: PRD-570
title: "Rename session_id to worker_id and emit worker lifecycle events"
kind: task
status: draft
priority: medium
effort: s
capability: moderate
parent:
depends_on: []
blocks: []
refines: "[[PRD-566-unified-event-log]]"
impacts:
  - src/darkfactory/event_log.py
  - src/darkfactory/graph_execution.py
  - src/darkfactory/runner.py
  - src/darkfactory/cli/run.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - events
  - observability
---

# Rename session_id to worker_id and emit worker lifecycle events

## Summary

The event log's `session_id` field is misnamed. It doesn't represent a user session — it represents a single `prd run` worker execution. Rename to `worker_id` throughout the codebase and emit the `worker_start`/`worker_finish` lifecycle events that PRD-566 designed but never implemented (originally called `session_start`/`session_finish`).

## Motivation

Each `prd run` invocation is a **worker** that picks up work and executes it. The current `session_id` name is confusing because:

- It's not a login session or a long-lived session
- It maps 1:1 to a worker process, not a user interaction
- When parallel execution lands (PRD-551), multiple workers will run concurrently — `worker_id` makes this model explicit

PRD-566 designed `session_start`/`session_finish` events but they were never emitted. These are worker lifecycle events: "I'm starting, here's my strategy and target" / "I'm done, here's my tally."

## Technical approach

### 1. Rename `session_id` → `worker_id`

Mechanical rename across:
- `event_log.py`: `generate_session_id()` → `generate_worker_id()`, field name in `EventWriter.__init__` and `emit()`
- `graph_execution.py`: parameter names, `EventWriter` construction
- `runner.py`: `run_workflow()` parameter
- `cli/run.py`: variable names, 3 call sites

The JSONL envelope field changes from `"session_id"` to `"worker_id"`. Existing event files are not migrated — they retain `session_id` as historical artifacts.

### 2. Emit `worker_start` / `worker_finish` events

Add to `cli/run.py` at each of the 3 execution paths (single PRD, queue drain, graph):

```python
# At start of execution
writer = EventWriter(repo_root, worker_id, prd_id="*")  # or first PRD
writer.emit("worker", "worker_start",
    command="run",
    strategy="single" | "queue" | "graph",
    target=prd_id or "--all",
    filters={...} if queue else None,
)

# At end of execution
writer.emit("worker", "worker_finish",
    completed=N,
    failed=N,
    skipped=N,
    success=all_succeeded,
)
```

Per PRD-566's design: "Session-level events are written to every per-PRD file that participates in that session." So `worker_start` goes into the first PRD's event file, and `worker_finish` into the last. Tools reconstruct the full worker view by globbing files with the same `worker_id`.

### 3. ID format

Change from `s-YYYYMMDD-HHMMSS-XXXX` to `w-YYYYMMDD-HHMMSS-XXXX` to make the prefix self-documenting.

## Acceptance criteria

- [ ] AC-1: `session_id` renamed to `worker_id` in all source code
- [ ] AC-2: JSONL envelope field is `"worker_id"` in newly written events
- [ ] AC-3: `generate_worker_id()` produces `w-YYYYMMDD-HHMMSS-XXXX` format
- [ ] AC-4: `worker_start` event emitted at the beginning of each `prd run --execute`
- [ ] AC-5: `worker_finish` event emitted at the end with completed/failed/skipped counts
- [ ] AC-6: All tests pass, mypy clean
- [ ] AC-7: Existing event files with `session_id` are not broken (just historical)

## References

- [[PRD-566-unified-event-log]] — original design that specified session_start/session_finish events
- [[PRD-551-parallel-graph-execution]] — future parallel workers make worker_id semantics clearer
