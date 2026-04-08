---
id: "PRD-220"
title: "Graph execution: walk DAG and run actionable PRDs"
kind: feature
status: draft
priority: high
effort: l
capability: complex
parent: null
depends_on: []
blocks: []
impacts:
  - src/darkfactory/cli.py
  - src/darkfactory/runner.py
  - src/darkfactory/graph.py
  - tests/test_graph_execution.py
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - execution
  - dag
---

# Graph execution: walk DAG and run actionable PRDs

## Summary

Today `prd run <PRD>` only handles a single leaf/runnable PRD. If you point it at an epic, it refuses. The user has to manually identify the next leaf, run it, wait, identify the next, run it, etc. — defeating the point of the harness.

This PRD adds **graph execution**: pass any PRD (epic, feature, or task) and the harness walks the dependency DAG + containment tree, finds actionable leaves under that root, and runs them in topological order. Optionally fans out to parallel worktrees when impacts don't conflict.

This is the original "run-chain" idea from the architecture plan, generalized: instead of a linear chain rooted at one PRD, it's a graph traversal that respects both `depends_on` ordering and `parent` containment.

## Motivation

The whole point of the harness is to remove the manual overhead of "pick next PRD → run → wait → pick next." Without graph execution, the user is still doing the orchestration by hand. With it, `prd run PRD-500` walks the entire darkfactory extraction epic to completion (or until something fails), reporting progress as each child lands.

## Requirements

1. `prd run <PRD>` accepts an epic, feature, or task. If the target has children, it walks them; if it's a leaf, it runs that single PRD (current behavior preserved).
2. Traversal respects `depends_on` — a PRD only runs once all its dependencies are in `done` or `review` status.
3. Traversal respects containment — the runner descends into children of the target, not arbitrary unrelated PRDs.
4. After each child completes, the runner re-loads the PRD set so any new children created by a `planning` workflow run show up immediately.
5. Failure of any single PRD halts that branch of the traversal but does not roll back completed siblings. The CLI exits non-zero with a summary of what landed and what's still outstanding.
6. `--max N` caps the number of PRDs run in one invocation (default: unbounded for `--execute`, 1 for `--dry-run`).
7. `--parallel` (opt-in) enables concurrent execution of independent siblings whose `impacts` don't overlap. Without this flag, execution is sequential.
8. Dry-run mode prints the planned traversal order without executing anything.
9. Status output is streamed: as each PRD starts/finishes, a line is printed (or JSON event with `--json`).

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

### Parallelism + impact conflicts

When `--parallel` is set and multiple PRDs are simultaneously ready, group them by `impacts_overlap` — PRDs in the same conflict group serialize, different groups run concurrently. Cap concurrency at `--parallel-jobs N` (default: number of CPUs / 2).

### Failure handling

If a leaf fails, mark its `status = blocked`, log the failure, and skip any PRDs whose `depends_on` includes the blocked one. Continue with PRDs in other branches of the traversal. This is the "halt this branch, keep going on others" semantics.

### Re-loading and planning workflows

After each completed PRD, re-call `load_all(prd_dir)`. This is critical: the planning workflow generates new child PRDs, and the next iteration of the traversal must see them. Without re-loading, an epic decomposed mid-run wouldn't have its children picked up.

### CLI surface

```
prd run <PRD-ID> [--execute] [--max N] [--parallel] [--parallel-jobs N] [--json]
```

The existing `prd run` is extended in place; no new subcommand. Single-leaf execution is just the degenerate case where the traversal yields exactly one PRD.

## Acceptance Criteria

- [ ] AC-1: `prd run <leaf-PRD>` behaves identically to today (single PRD execution).
- [ ] AC-2: `prd run <epic>` walks the epic's leaves and runs each in topological order.
- [ ] AC-3: A PRD with unsatisfied `depends_on` is skipped until its dependency completes.
- [ ] AC-4: A failed PRD's downstream dependents are skipped; unrelated branches continue.
- [ ] AC-5: `--max N` halts after N PRDs complete (success or failure).
- [ ] AC-6: `--dry-run` (default) prints the traversal plan without invoking agents.
- [ ] AC-7: After a planning workflow generates new children, the next iteration picks them up without restarting the command.
- [ ] AC-8: `--parallel` runs siblings concurrently when their `impacts` don't conflict.
- [ ] AC-9: Conflicting siblings serialize even with `--parallel`.
- [ ] AC-10: Final exit code is 0 if every traversed PRD succeeded, non-zero otherwise.
- [ ] AC-11: Tests cover: linear chain, branching epic, depends_on cross-edges, mid-run planning decomposition, failure isolation, parallel grouping by impacts.

## Open Questions

- [ ] How should the traversal report progress to the user? Plain stdout lines vs structured JSON events vs a TUI? Default to stdout lines + `--json` for structured.
- [ ] Should `--parallel` be the default once it's stable? Probably not — explicit opt-in is safer for a tool that creates worktrees and PRs.
- [ ] How does this interact with stacked PRs? Each leaf gets its own branch; should branches base on the previous leaf's branch (true stack) or all on `main` (independent PRs)? Probably configurable, default `main`-based.
- [ ] Can a single `prd run` invocation span multiple Claude Code agent sessions? Yes — each leaf is a fresh agent invocation.

## References

- [[PRD-500-darkfactory-extraction]] — first real consumer; epic execution would walk PRDs 501..505 in order
- The original "run-chain" idea in the harness architecture plan
