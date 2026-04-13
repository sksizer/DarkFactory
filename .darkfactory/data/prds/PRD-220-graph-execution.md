---
id: PRD-220
title: "Graph execution: walk DAG and run actionable PRDs"
kind: feature
status: done
priority: high
effort: l
capability: complex
parent:
depends_on: []
blocks: []
impacts:
  - python/darkfactory/cli.py
  - python/darkfactory/runner.py
  - python/darkfactory/graph_execution.py
  - tests/test_graph_execution.py
  - prds/README.md
workflow:
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - execution
  - dag
  - feature
---

# Graph execution: walk DAG and run actionable PRDs

## Summary

Today `prd run <PRD>` only handles a single leaf/runnable PRD. If you point it at an epic, it refuses. The user has to manually identify the next leaf, run it, wait, identify the next, run it, etc. — defeating the point of the harness.

This PRD adds **graph execution**: pass any PRD (epic, feature, or task) and the harness walks the dependency DAG + containment tree, finds actionable leaves under that root, and runs them in topological order.

This is the original "run-chain" idea from the architecture plan, generalized: instead of a linear chain rooted at one PRD, it's a graph traversal that respects both `depends_on` ordering and `parent` containment.

## Scope (this PRD)

**Sequential only.** Parallel execution is intentionally deferred to [[PRD-551-parallel-graph-execution]]. This keeps the first landing small and delivers the main value (hands-off multi-PRD execution) without the coordination complexity of parallel worktrees.

**Single-dep stacking.** When a PRD has exactly one unmet dependency that just completed in this invocation, its worktree bases on that dependency's branch (true stack). Independent siblings base on `main`. **Multi-dep PRDs error** with a pointer to [[PRD-552-merge-upstream-task]], which will add the merge-upstream task needed to safely base a PRD on ≥2 upstream branches.

**Permission enforcement deferred.** [[PRD-553-child-creation-permission]] will add explicit `can_create_prds` permissions so `--max-runs` honestly caps DAG growth. Until it lands, graph execution trusts workflows not to silently generate child PRDs from tasks that shouldn't.

**Downstream stale-PRD flagging.** When a PRD completes and touches files listed in other PRDs' `impacts:`, those PRDs should be flagged stale. That's [[PRD-550-upstream-impact-propagation]] — PRD-220 will include enough information in its run events for PRD-550 to consume later.

## Motivation

The whole point of the harness is to remove the manual overhead of "pick next PRD → run → wait → pick next." Without graph execution, the user is still doing the orchestration by hand. With it, `prd run PRD-500` walks the entire darkfactory extraction epic to completion (or until something fails), reporting progress as each child lands.

## Requirements

1. `prd run <PRD>` accepts an epic, feature, or task. If the target has children, it walks them; if it's a leaf, it runs that single PRD (current behavior preserved).
2. Traversal respects `depends_on` — a PRD only runs once all its dependencies are in `done` or `review` status.
3. Traversal respects containment — the runner descends into children of the target, not arbitrary unrelated PRDs.
4. After each child completes, the runner re-loads the PRD set so any new children created by a `planning` workflow run show up immediately.
5. Failure of any single PRD halts that branch of the traversal but does not roll back completed siblings. The CLI exits non-zero with a summary of what landed and what's still outstanding.
6. `--max-runs N` caps the total number of PRD runs (success *or* failure) in one invocation, **including PRDs introduced mid-run** by planning workflows. Default: unbounded. In dry-run the full DAG is always printed regardless of the cap; a separate "execution slice" section shows what would actually run under the cap.
7. Execution is **sequential** in this PRD. Parallelism is out of scope (see PRD-551).
8. Dry-run mode prints:
   - **Full DAG** — every PRD at-or-below the root plus its transitive unmet deps.
   - **Execution slice** — the ordered subset that will actually run under `--execute` + current `--max-runs`.
9. Status output is streamed: as each PRD starts/finishes, a line is printed (or a JSON event with `--json`).
10. **Single-dep stacking:** when a PRD has exactly one `depends_on` entry and that dep completed in this invocation, the PRD's worktree bases on the dep's branch. Otherwise it bases on the session `--base` (default `main`).
11. **Multi-dep error:** when a PRD has ≥2 `depends_on` entries that aren't already merged to `main`, it is skipped with a structured error pointing at PRD-552. Its dependents are also skipped. Other branches continue.
12. **Failure handling:** a failed PRD is set to `status=blocked`, its transitive dependents (by `depends_on`) are skipped with reason `blocked_by=<id>`, unrelated branches continue, and the CLI exits non-zero with a summary.
13. **Downstream propagation (capture only):** see PRD-550. PRD-220 surfaces `{prd_id, changed_files}` per run event so PRD-550 can consume it — no enforcement in this PRD.

## Technical Approach

### Traversal algorithm

```python
def actionable_descendants(root: PRD, prds: dict[str, PRD]) -> list[PRD]:
    """All runnable PRDs at-or-below `root` in topological order."""
    candidates = [root] + descendants(root.id, prds)
    leaves = [p for p in candidates if not children(p.id, prds)]
    # topological sort restricted to leaves, edges from depends_on
    return topo_sort(leaves, edges=depends_on_edges(leaves))
```

### Execution loop

```python
def execute_graph(root: PRD, prds: dict, max_runs: int, parallel: bool) -> ExecutionReport:
    completed: list[str] = []
    failed: list[tuple[str, str]] = []
    while True:
        prds = load_all(prd_dir)  # re-load to pick up planning-workflow children
        ready = [p for p in actionable_descendants(root, prds)
                 if p.status == "ready" and deps_satisfied(p, prds)]
        if not ready:
            break
        if len(completed) + len(failed) >= max_runs:
            break
        batch = pick_batch(ready, parallel)  # 1 PRD or N non-conflicting PRDs
        results = run_batch(batch)
        completed.extend(r.prd_id for r in results if r.success)
        failed.extend((r.prd_id, r.reason) for r in results if not r.success)
    return ExecutionReport(completed=completed, failed=failed)
```

### Failure handling

If a leaf fails, mark its `status = blocked`, log the failure, and skip any PRDs whose `depends_on` includes the blocked one. Continue with PRDs in other branches of the traversal. This is the "halt this branch, keep going on others" semantics.

### Re-loading and planning workflows

After each completed PRD, re-call `load_all(prd_dir)`. This is critical: the planning workflow generates new child PRDs, and the next iteration of the traversal must see them. Without re-loading, an epic decomposed mid-run wouldn't have its children picked up.

### CLI surface

```
prd run <PRD-ID> [--execute] [--max-runs N] [--json] [--base REF] [--model M]
```

The existing `prd run` is extended in place; no new subcommand. Single-leaf execution is just the degenerate case where the traversal yields exactly one PRD.

### Stacked branch base resolution

```
def resolve_base(prd, completed_this_run, default_base):
    unmet = [d for d in prd.depends_on if d not in already_merged_to_main]
    if len(unmet) == 0:
        return default_base             # independent — base on main
    if len(unmet) == 1 and unmet[0] in completed_this_run:
        return branch_for(unmet[0])     # single-dep stack
    # ≥2 unmet deps → multi-dep error (PRD-552)
    raise MultiDepUnsupported(prd.id, unmet)
```

## Acceptance Criteria

- [ ] AC-1: `prd run <leaf-PRD>` behaves identically to today (single PRD execution).
- [ ] AC-2: `prd run <epic>` walks the epic's leaves and runs each in topological order.
- [ ] AC-3: A PRD with unsatisfied `depends_on` is skipped until its dependency completes.
- [ ] AC-4: A failed PRD's downstream dependents are skipped; unrelated branches continue.
- [ ] AC-5: `--max-runs N` halts after N PRDs complete (success or failure), counting PRDs introduced mid-run.
- [ ] AC-6: `--dry-run` (default) prints the full DAG and the execution slice without invoking agents.
- [ ] AC-7: After a planning workflow generates new children, the next iteration picks them up without restarting the command.
- [ ] AC-8: A PRD with a single completed-this-run dependency has its worktree based on that dependency's branch (stacked).
- [ ] AC-9: A PRD with ≥2 unmerged dependencies errors with a pointer to PRD-552 and is skipped; its dependents are also skipped.
- [ ] AC-10: Final exit code is 0 if every traversed PRD succeeded, non-zero otherwise.
- [ ] AC-11: Tests cover: linear chain, branching epic, depends_on cross-edges, mid-run planning decomposition, failure isolation, single-dep stacked base, multi-dep error, `--max-runs` cutoff including introduced PRDs.

## Open Questions

- [ ] Progress output format: default to stdout lines + `--json` for structured. Confirmed.
- [ ] Integration branches for independent siblings under an epic: explicitly rejected — each sibling bases on `main` unless there's an explicit `depends_on` edge.
- [ ] Can a single `prd run` invocation span multiple Claude Code agent sessions? Yes — each leaf is a fresh agent invocation.

## References

- [[PRD-500-darkfactory-extraction]] — first real consumer; epic execution would walk PRDs 501..505 in order
- [[PRD-550-upstream-impact-propagation]] — consumes per-run file changes to flag stale downstream PRDs
- [[PRD-551-parallel-graph-execution]] — parallel execution follow-up
- [[PRD-552-merge-upstream-task]] — unblocks multi-dep case
- [[PRD-553-child-creation-permission]] — tightens `--max-runs` honesty
- The original "run-chain" idea in the harness architecture plan
