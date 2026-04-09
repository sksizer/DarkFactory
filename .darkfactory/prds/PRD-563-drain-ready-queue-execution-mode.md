---
id: PRD-563
title: "Drain-ready-queue execution mode: run all ready PRDs without a target"
kind: feature
status: draft
priority: high
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-220-graph-execution]]"
blocks: []
impacts:
  - src/darkfactory/graph_execution.py
  - src/darkfactory/cli.py
  - tests/test_drain_ready_queue.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: 2026-04-09
tags:
  - harness
  - execution
  - dag
---

# Drain-ready-queue execution mode: run all ready PRDs without a target

## Summary

Today `prd run` requires a target PRD. If the target is an epic it walks its children; if it's a leaf it runs that one PRD. But there's no way to say "just work through everything that's ready." The user has to pick a target, wait, pick another, repeat — exactly the manual orchestration the harness is supposed to eliminate.

This PRD adds a **target-free execution mode** that discovers all `ready` PRDs across the entire repo, respects their `depends_on` ordering, and runs them sequentially until the queue is empty (or a cap is hit).

## Motivation

The current graph traversal is rooted: you must name an epic or leaf to start from. This is useful when you want to focus on one initiative, but it doesn't cover the common case of "I have 8 ready PRDs across 3 different epics — just start working." Forcing the user to identify and sequence those manually is overhead the harness should absorb.

This is especially valuable for:

- **Overnight / background runs.** Kick off `prd run --all --execute --max-runs 10` and let the harness chew through whatever's ready.
- **CI integration.** A scheduled job that drains the ready queue daily.
- **Onboarding.** A new contributor can run `prd run --all` to see the full picture of what's actionable without needing to know the PRD graph.

## Requirements

1. **`prd run --all`** (no positional PRD-ID) discovers every PRD with `status: ready` whose `depends_on` are all satisfied (`done` or `review`).
2. The discovered set is topologically sorted by `depends_on`. PRDs with no dependency relationship between them are ordered by priority (high > medium > low), then by PRD number (ascending, i.e. oldest first).
3. Execution is sequential, reusing the same loop from PRD-220: run one PRD, re-load the PRD set, pick the next ready PRD, repeat.
4. Re-loading between runs means:
   - A PRD that transitions to `ready` mid-run (e.g. its only dependency just completed) is picked up.
   - A planning workflow that generates new `ready` children has those children picked up.
5. **`--max-runs N`** caps total runs, same semantics as PRD-220. Default: unbounded.
6. **`--priority P`** filters to PRDs at or above a given priority. E.g. `--priority high` skips medium/low PRDs even if they're ready.
7. **`--tag T`** filters to PRDs with a specific tag. Repeatable for OR semantics (`--tag harness --tag execution` runs PRDs with either tag).
8. **`--exclude PRD-ID`** excludes specific PRDs (and their dependents if the exclusion breaks their deps). Repeatable.
9. **Dry-run** (default, no `--execute`) prints the ordered queue: which PRDs would run, in what order, and why (deps satisfied, priority, filters applied).
10. **Failure handling** follows PRD-220 semantics: a failed PRD is marked `blocked`, its dependents are skipped, unrelated PRDs continue. The run exits non-zero if any PRD failed.
11. **Interaction with rooted execution.** `prd run <PRD-ID>` continues to work exactly as before. `--all` is simply an alternative to naming a target. They are mutually exclusive; passing both is an error.
12. **Stacked branches** follow the same single-dep stacking rule from PRD-220. A ready PRD whose single dependency just completed in this run bases on that dependency's branch.

## Technical approach

### Discovery

```python
def discover_ready_queue(prds: dict[str, PRD], filters: QueueFilters) -> list[PRD]:
    """All ready PRDs with satisfied deps, filtered and sorted."""
    ready = [
        p for p in prds.values()
        if p.status == "ready"
        and deps_satisfied(p, prds)
        and matches_filters(p, filters)
    ]
    return topo_sort_with_tiebreak(ready, key=lambda p: (p.priority_rank, p.number))
```

### Integration with existing execution loop

The PRD-220 `execute_graph` loop already has the shape: load PRDs, find ready set, pick next, run, re-load, repeat. The change is in how the initial candidate set is determined:

- **Rooted mode** (existing): candidates = `actionable_descendants(root, prds)`
- **Queue mode** (new): candidates = `discover_ready_queue(prds, filters)`

The execution loop itself is identical. Factor the candidate-selection into a strategy so both modes share the same run/re-load/fail logic.

### CLI surface

```
# Drain the ready queue (dry-run)
prd run --all

# Execute up to 5 ready PRDs
prd run --all --execute --max-runs 5

# Only high-priority PRDs
prd run --all --execute --priority high

# Only PRDs tagged "harness"
prd run --all --execute --tag harness

# Exclude a known-broken PRD
prd run --all --execute --exclude PRD-999
```

### Ordering rationale

Topological sort ensures dependencies run before dependents. The tiebreak (priority then PRD number) means high-priority work lands first, and within the same priority older PRDs are preferred — they've been waiting longest.

## Acceptance criteria

- [ ] AC-1: `prd run --all` discovers all `ready` PRDs with satisfied dependencies and prints the ordered queue (dry-run).
- [ ] AC-2: `prd run --all --execute` runs the queue sequentially, re-loading PRDs between runs.
- [ ] AC-3: A PRD whose dependency completes mid-run is picked up in subsequent iterations.
- [ ] AC-4: `--max-runs N` caps total runs.
- [ ] AC-5: `--priority P` filters to PRDs at or above the given priority.
- [ ] AC-6: `--tag T` filters to PRDs with a matching tag (OR across multiple `--tag` flags).
- [ ] AC-7: `--exclude PRD-ID` excludes specific PRDs and skips their dependents if deps are broken.
- [ ] AC-8: `prd run --all <PRD-ID>` is a hard error (mutually exclusive).
- [ ] AC-9: Failure handling matches PRD-220: failed PRD is blocked, dependents skipped, unrelated PRDs continue, exit non-zero.
- [ ] AC-10: Ordering is topological with priority-then-number tiebreak.
- [ ] AC-11: Tests cover: empty queue, single ready PRD, multiple independent PRDs ordered by priority, dependency chain unlocked mid-run, filter combinations, exclusion, max-runs cutoff, failure isolation.

## Open questions

- [ ] Should `--all` be the flag name, or should it be a subcommand like `prd drain`? `--all` is more discoverable as a modifier of the existing `run` command. A dedicated subcommand risks fragmenting the CLI surface. **Recommendation: `--all` flag.**
- [ ] Should there be a `--watch` / `--continuous` mode that polls for newly-ready PRDs after the queue empties? Useful for long-running daemon-style execution, but adds complexity. **Recommendation: defer to a follow-up PRD.**
- [ ] Interaction with PRD-551 (parallel execution). The queue mode is a natural fit for parallel execution — independent PRDs with non-overlapping impacts could run concurrently. But PRD-551 is about parallelism within rooted traversal. Extending it to queue mode should be straightforward once both land. **Recommendation: sequential only in this PRD, parallel queue mode in a PRD-551 follow-up.**

## References

- [[PRD-220-graph-execution]] — the sequential rooted execution this extends.
- [[PRD-551-parallel-graph-execution]] — parallel execution, natural next step for queue mode.
- [[PRD-555-backlog-review-workflow]] — complementary: review hygiene ensures the ready queue is healthy before draining it.
