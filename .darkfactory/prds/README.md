# Harness Dev PRDs

A parallel PRD set for tracking the harness's own development work. These PRDs use the same schema as `docs/prd/` but live here so they travel with the tool when it's extracted into a standalone repo.

Stored separately from the canonical project PRDs so:
- Harness development doesn't pollute the pumice project tracking
- When `tools/prd-harness/` is extracted, its work history comes along
- We can dogfood the harness against its own work as a rough prototype before wiring up the full workflow executor

## ID scheme

Dev PRDs use the `PRD-2NN` range to avoid collision with the canonical set (which currently tops out at PRD-110). When the harness is extracted, the numbers can be renumbered freely since nothing outside this directory references them.

## Running the harness against these

```bash
just prd-dev status
just prd-dev tree PRD-200
just prd-dev next --limit 5
```

The `prd-dev` justfile recipe forwards to the harness with `--prd-dir tools/prd-harness/dev-prds`.

## Using them to drive work

The current workflow is manual dogfooding — pick a PRD, implement it, flip its status from `ready` → `in-progress` → `review` by editing the frontmatter. Once the workflow executor (PRD-210/PRD-211) lands, we can automate this by running `just prd-dev run PRD-201 --execute` and letting the harness orchestrate.

## Graph execution (PRD-220)

`prd run <PRD>` accepts any PRD — leaf, feature, or epic — and walks the dependency DAG from that root:

```bash
# Dry-run: print the full DAG and the execution slice that would run.
prd run PRD-500

# Execute: walk the DAG sequentially, running each actionable leaf.
prd run PRD-500 --execute

# Cap the number of runs (counts successes, failures, and mid-run introduced PRDs).
prd run PRD-500 --execute --max-runs 3

# Stream structured events.
prd run PRD-500 --execute --json
```

Scope rules:

- **Leaf with deps satisfied** → legacy single-PRD path (one worktree, one run).
- **Epic/feature with children, or leaf with unmet deps** → graph execution. The executor walks `{root} ∪ containment descendants ∪ transitive unmet-dependency closure` in topological order.
- **Single-dep stacking:** a PRD with exactly one dependency that completed earlier in this invocation has its worktree based on that dependency's branch. Independent siblings base on `--base` (default `main`).
- **Multi-dep PRDs are skipped** with a pointer to [[PRD-552-merge-upstream-task]] — they need a merge-upstream task before they can be safely based on ≥2 upstream branches.
- **Failure handling:** a failed PRD is set to `status=blocked` and its transitive dependents are skipped. Unrelated branches continue. Exit code is non-zero if any PRD failed.
- **Mid-run DAG growth:** PRDs are re-loaded between runs, so planning workflows that generate children mid-invocation have those children picked up automatically. `--max-runs` counts introduced PRDs against the cap.

Graph execution is **sequential** in this first landing. Parallel fan-out is [[PRD-551-parallel-graph-execution]].
