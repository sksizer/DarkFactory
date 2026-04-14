---
id: PRD-552
title: Merge-upstream task for PRDs with multiple dependencies
kind: feature
status: draft
priority: high
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-549-builtins-package-split]]"
blocks:
  - "[[PRD-220-graph-execution]]"
impacts:
  - python/darkfactory/builtins/merge_upstream.py
  - python/darkfactory/runner.py
  - workflows/
  - tests/test_merge_upstream.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - execution
  - merge
  - agent
  - feature
---

# Merge-upstream task for PRDs with multiple dependencies

## Summary

When a PRD declares `depends_on: [A, B, C]` and we want its worktree to *actually* build on top of all three upstream branches (not just `main`, not just one of them), we need a task that:

1. Performs a best-effort git merge of N upstream branches into the new worktree.
2. If conflicts arise, hands them to an agent to resolve.
3. Runs quality checks (`just test`, `just lint`, `just typecheck`, `just format-check`) against the merged state before the downstream PRD's actual work begins.

This is a prerequisite for PRD-220's "stacked branches with multi-parent dependencies" behavior.

## Motivation

PRD-220 asks: "if D has `depends_on: [A, B]`, what branch does D's worktree base on?" Basing on `main` loses A and B's work (defeats stacking). Basing on just one loses the other. The correct answer is "a merge of A and B." Doing that by hand is exactly the kind of work the harness should absorb.

## Requirements

1. **New builtin:** `merge_upstream(ctx, branches: list[str], strategy: str = "recursive")`.
   - Runs `git merge --no-ff` for each branch in order (or `git merge` of all branches in one invocation — decide based on conflict ergonomics).
   - On clean merge: commits the merge and continues.
   - On conflict: leaves the conflict markers in place and raises a structured `MergeConflict` error with paths + hunks.
2. **Workflow integration:** a new workflow task type (or reuse ShellTask with `on_failure="retry_agent"` semantics) that:
   - Calls `merge_upstream`.
   - On `MergeConflict`, invokes an agent with the conflict context + instruction "resolve these conflicts and run `just test && just lint && just typecheck`."
   - On agent success, the merge commit is the new base for the downstream PRD's work.
   - On agent failure, the PRD is marked `blocked` with the conflict summary.
3. **Graph executor integration:** PRD-220's executor calls this task automatically when a PRD has ≥2 unmet-but-now-complete dependencies. Single-dep case stays simple (direct branch base, no merge task needed).
4. **Quality gates post-merge:** the merge task runs the standard quality suite against the merged state before the downstream PRD proceeds. A merge that passes mechanically but breaks tests is still a failure.
5. **Idempotency:** if the merge task runs twice in the same worktree (retry), it detects the existing merge commit and skips.

## Technical approach

- Builtin lives at `python/darkfactory/builtins/merge_upstream.py` (aligns with PRD-549's per-builtin-module convention if that lands first).
- Conflict payload structure: `{"files": [...], "hunks": {path: [<hunk>]}}` — enough for an agent to understand the scope without re-reading git state.
- Agent prompt template lives under `workflows/` as a reusable fragment.
- Test strategy: fixture repos with pre-scripted conflicts (clean 3-way merge, trivial conflict, unresolvable conflict, test-breaking merge).

## Open questions

- [ ] Should the merge task create an explicit "integration" commit with a message enumerating the merged branches, or rely on git's default merge message? Explicit is better for audit.
- [ ] Which base do we merge *into*? `main`? Or the union ancestor of A/B/C? I think `main` is right: start from main, merge A, merge B, merge C — this is the natural integration point.
- [ ] Budget for agent conflict resolution — how many retries? How much context? Probably 1 retry with full conflict context, then blocked.
- [ ] Does this task belong to a workflow, or is it always auto-inserted by the graph executor? Probably the latter — it's a harness concern, not a user-facing workflow step.
- [ ] Interaction with PRD-545 (harness-driven rebase / conflict resolution) — overlaps substantially. Possibly merge these PRDs, or have PRD-552 call into PRD-545's machinery.

## References

- [[PRD-220-graph-execution]] — blocked by this for multi-dep cases.
- [[PRD-545-harness-driven-rebase-and-conflict-resolution]] — overlapping conflict-resolution concern.
- [[PRD-549-builtins-package-split]] — sibling children all touching `builtins.py` is the exact scenario this task is designed for.

## Assessment (2026-04-11)

- **Value**: 2/5 — the target scenario ("PRD D has depends_on: [A, B, C]
  and needs to be based on the merge of all three") has never actually
  appeared in practice. Every real multi-dep PRD in the current backlog
  has at most one non-trivial dependency; the others are "also on main."
  A pre-emptive merge-upstream task would ride idle 95% of the time.
- **Effort**: m — new builtin (`merge_upstream.py`), agent conflict
  prompt, graph executor hook, fixture-based conflict tests. Overlaps
  heavily with PRD-545's Phase 2/3 — if both were built, `merge_upstream`
  would largely be a thin wrapper over PRD-545's machinery.
- **Current state**: greenfield. No `merge_upstream.py` in builtins,
  no workflow integration.
- **Gaps to fully implement**: all of it.
- **Recommendation**: defer until an actual 3-dep PRD surfaces. When
  one does, consider whether PRD-545's scheduler machinery covers it
  and this PRD becomes redundant. The `blocks: [PRD-220-graph-execution]`
  edge is aspirational — PRD-220 shipped without this and is working.
  Clear the `blocks` edge.
