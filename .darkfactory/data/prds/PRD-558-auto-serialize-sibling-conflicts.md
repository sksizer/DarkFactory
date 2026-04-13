---
id: PRD-558
title: Auto-serialize sibling PRDs with overlapping impacts to avoid hand-resolved merge conflicts
kind: feature
status: draft
priority: high
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/graph_execution.py
  - src/darkfactory/impacts.py
  - src/darkfactory/cli/_parser.py
  - src/darkfactory/cli/run.py
  - tests/test_graph_execution.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-11'
tags:
  - harness
  - execution
  - dag
  - merge-conflicts
  - ergonomics
  - feature
---

# Auto-serialize sibling PRDs with overlapping impacts to avoid hand-resolved merge conflicts

## Summary

When an epic decomposes into N sibling children that all touch the same file(s), running them in parallel produces merge conflicts on every sibling after the first lands. The conflicts are individually trivial (mostly "union the imports, accept non-overlapping deletions") but resolving them by hand N times is laborious, error-prone, and scales linearly with the fan-out of every modularization epic. This PRD captures the problem and lays out several candidate approaches without committing to one — the solution space needs more discussion before picking.

## Motivation

Concrete incident (2026-04-09): PRD-549 decomposed into 9 children (PRD-549.3–549.11), each moving one builtin from `src/darkfactory/builtins/__init__.py` into its own submodule. Every child deletes a different function from the same file and adds a `from .<name> import <func>` line to the same import block. Git's 3-way merge handles the non-overlapping deletions *most* of the time, but the import-block edits collide reliably, so each child-after-the-first needs a hand-resolved rebase. The resolutions are mechanical — always the same shape — but doing it nine times is exhausting.

PRD-556 (cli.py split) has **18 children** with the same structure. PRD-557 (runner.py split) has 4. Every future modularization epic will look the same. Without a general fix, the cost of "split a big file into a package" scales with `O(n)` hand-rebases where `n` is the fan-out.

The frustration is captured in the user's words: *"it is easy merge conflicts [...] but it is laborious to do it."*

### Why the conflicts happen (precisely)

For a fan-out against a shared file like `builtins/__init__.py`:

1. Each child deletes a different function body — git usually merges these cleanly.
2. Each child adds an import line at the top — **every child touches the same lines**, reliably colliding.
3. Each child may touch `__all__` or a similar flat list — same collision pattern.
4. Git's hunk-context heuristic can merge adjacent function deletes as overlapping when they share blank lines — sporadic false conflicts.

The first category is rare. The second is guaranteed. The third is common. The fourth is sporadic.

## The general pattern

When **two sibling PRDs under the same parent epic** have overlapping entries in their `impacts:` frontmatter fields, the harness knows they *will* conflict. Today, the graph executor ignores this information — siblings with no explicit `depends_on` edge are treated as independently runnable, so they can land in any order, and the second-to-land pays the rebase cost.

The goal of this PRD is to make the harness use the information it already has (declared `impacts:`, the `impacts.py` overlap detection from PRD-546 territory, and PRD-220's graph executor) to avoid hand-resolved conflicts in the common modularization-epic case.

### The data is already being surfaced

**`prd validate` already emits warnings for this exact case.** Running `uv run prd validate` against the current main shows entries like:

```
WARN:  PRD-556.5 and PRD-556.9 have overlapping impacts (1 files) but no explicit dependency
WARN:  PRD-556.6 and PRD-556.7 have overlapping impacts (1 files) but no explicit dependency
WARN:  PRD-556.6 and PRD-556.8 have overlapping impacts (1 files) but no explicit dependency
... (7 warnings total just for PRD-556's children)
```

So the overlap detection is already implemented and wired into `prd validate`. This PRD is not about *computing* the conflict set — that's done. It's about *acting* on it at execution time instead of just printing a warning and letting humans absorb the cost. That significantly de-risks any chosen option: the hard part (detecting overlaps reliably) already works.

## Candidate approaches

Multiple options. Tradeoffs differ on ergonomics, implementation effort, and how much they preserve the original "parallel stress test" intent of epics like PRD-549. **Status of this PRD is draft because the right pick isn't obvious yet — it depends on how PRD-551 (parallel execution) and PRD-552 (merge-upstream task) shake out, and on whether we want the harness to be opinionated or just helpful.**

### Option 1 — Auto-inject phantom `depends_on` at scheduling time

When the executor is about to pick the next PRD to run, it computes `impacts_overlap` against every other ready sibling under the same parent. If any overlap exists, it picks an order (deterministic, e.g. by PRD id) and treats the lower-id sibling as a phantom `depends_on` of the higher-id one for the duration of the run. No PRD files are modified; the serialization is purely in-memory.

- **Pro:** zero change to PRD authoring. Epics keep their natural "9 independent children" shape. The harness handles ordering silently.
- **Pro:** uses existing `impacts_overlap()` + PRD-220's single-dep stacking path. Minimal new code.
- **Pro:** sequential-only today (PRD-220). Fits naturally into the current executor.
- **Con:** opaque to the PRD author — "why is 549.4 waiting?" requires reading logs.
- **Con:** the phantom edges aren't visible in `prd tree` / `prd status` output unless we also surface them.
- **Con:** deterministic ordering-by-id is arbitrary. If the author wanted a different order they have to add explicit `depends_on` and override.

### Option 2 — Persist inferred `depends_on` edges into the PRD files

Same overlap detection, but the inferred edge is written back to the downstream PRD's `depends_on:` frontmatter as a visible wikilink. The edit is a harness builtin (e.g. `auto_serialize_siblings`) that runs at plan time, not run time.

- **Pro:** the graph is visible. `prd tree` shows the serial chain.
- **Pro:** the author can override by editing the file after the fact.
- **Con:** mutates PRD files, which is noise in git history.
- **Con:** requires re-running the auto-serializer whenever siblings are added/removed.
- **Con:** what happens if the impacts change later? The previously-inferred edge may become stale.

### Option 3 — Additive-first pattern as a documented epic convention

Don't change the executor at all. Instead, change how modularization epics are authored: children only *add* new files, never edit the shared monolith. A final "atomic switch" child does all the destructive edits in one commit.

- **Pro:** no harness changes. The pattern itself eliminates the conflict.
- **Pro:** children are truly independent and can run in parallel (relevant once PRD-551 lands).
- **Con:** requires a convention every modularization-epic author remembers. The planning workflow prompt (see PRD-554) would need a section on it.
- **Con:** temporary duplication of code during the parallel phase (function exists in both monolith and new module until the atomic switch lands).
- **Con:** colocated tests test an unregistered/unwired function during the parallel phase — slightly unnatural.
- **Con:** the "atomic switch" child still touches every new module (to add `@builtin` decorators, or to rewrite `__init__.py`) — bigger single diff than the status quo.

### Option 4 — Custom git merge driver for flat import/export lists

Configure `.gitattributes` so that files like `builtins/__init__.py` (and `cli/__init__.py`, etc.) use a custom merge driver that understands "flat list of import lines" and takes the union automatically.

- **Pro:** transparent to the author and executor. Git just handles the merge.
- **Pro:** works for hand-rebases outside the harness too.
- **Con:** writing a reliable merge driver is finicky. The file has to follow a known shape; any hand-authored deviation (module docstring, conditional imports, grouped imports) breaks it.
- **Con:** only covers the import-block half of the problem. The "delete function bodies" half still relies on git's default 3-way merge.
- **Con:** adds a Python script or similar to the repo that has to be installed per-clone.

### Option 5 — Harness-driven auto-rebase with known-resolution machinery

Build out PRD-545 (harness-driven rebase and conflict resolution). When a sibling lands, the harness auto-rebases every in-flight sibling onto the new main and resolves conflicts using a library of "known patterns" (union of imports, non-overlapping deletions, etc.).

- **Pro:** the most general solution. Handles arbitrary conflict shapes, not just the shared-import-block one.
- **Pro:** useful far beyond modularization epics — any parallel PR conflict benefits.
- **Con:** PRD-545 is large and complex. This is a serious amount of work.
- **Con:** "known patterns" is a bottomless rabbit hole. Every new shape is a new pattern to write and test.
- **Con:** risk of auto-resolving conflicts incorrectly is real — a false "resolved" is worse than a true conflict.

### Option 6 — `git rerere` (reuse recorded resolution)

Enable `rerere` in the repo and teach the harness to replay recorded resolutions during rebase. Once the first hand-resolution is captured, subsequent identical conflicts are resolved automatically.

- **Pro:** built into git. No custom code.
- **Pro:** works for any conflict shape, not just modularization.
- **Con:** requires one hand-resolution per conflict pattern before automation kicks in — still laborious for the first time in every new modularization epic.
- **Con:** rerere's "identical" heuristic is strict; small variations (different line numbers, different surrounding context) can miss.
- **Con:** recorded resolutions aren't shared across clones by default — would need to live in a tracked location.

## Recommended scope (if built)

If we do build a solution, the minimum viable version is probably **Option 1 (auto-inject phantom `depends_on`)**, because:

- It reuses infrastructure that already exists (PRD-220 stacking, `impacts_overlap()` from PRD-546 territory).
- It doesn't require a new convention, new file formats, new merge drivers, or new rebase machinery.
- It degrades gracefully — if the overlap detection has false negatives, you get the current behavior. If it has false positives, you get safer-than-necessary serialization.

**Option 3 (additive-first convention)** is a good complement rather than an alternative: even with auto-serialization, modularization epics authored additively are faster (can eventually run in parallel under PRD-551). So the recommendation would be "build Option 1 as the safety net, document Option 3 as the preferred authoring style."

None of this is settled. The open questions below need discussion before committing.

## Open questions

- [ ] **Which approach?** Tradeoffs above. No single clear winner.
- [ ] **Interaction with PRD-551 (parallel execution).** Option 1 is trivial under sequential-only PRD-220. Under PRD-551, it has to become "group overlapping siblings into a serial lane while non-overlapping siblings run in parallel." Still straightforward but needs PRD-551's scheduler to exist first.
- [ ] **Interaction with PRD-552 (merge-upstream task).** If we build PRD-552, do we still need Option 1? PRD-552 adds the ability to base a PRD on ≥2 upstream branches with agent-assisted conflict resolution. That's a different shape — it handles "PRD D depends on both A and B" rather than "A and B conflict with each other." Both problems coexist.
- [ ] **Interaction with PRD-546 (impact declaration drift detection).** Shares file-overlap computation. Make sure both consume the same helper.
- [ ] **Interaction with PRD-550 (upstream impact propagation).** PRD-550 flags downstream PRDs as stale when an upstream merges. PRD-558 proactively avoids that by ordering. Complementary, not competing.
- [ ] **What counts as "sibling"?** Same parent epic only, or any PRDs with overlapping impacts regardless of parent? Sibling-only is safer (preserves cross-epic independence) but misses the cross-epic overlap case. Start with sibling-only.
- [ ] **Visible or invisible serialization?** Option 1 is invisible, Option 2 is visible. Visible is more auditable but noisier in PRD files.
- [ ] **False-positive tolerance.** If the `impacts:` fields are wrong (PRD-546 concern), auto-serialization can over-serialize unnecessarily. How loudly should we warn?
- [ ] **Manual override escape hatch.** If the author *wants* two siblings to race each other (for harness stress-testing), how do they opt out? A `no_auto_serialize: true` frontmatter flag? A CLI `--no-auto-serialize`?
- [ ] **Authoring-time vs run-time detection.** Should `prd validate` flag overlapping siblings as a warning so authors notice during planning, not when execution starts?
- [ ] **Retroactive application.** Should this apply to existing draft/ready PRDs on first run, or only to PRDs created after the feature lands?

## Acceptance criteria (tentative — will sharpen when an option is picked)

- [ ] AC-1: When two sibling PRDs with overlapping `impacts:` are both in `status=ready`, the executor runs them in a deterministic order (whichever option is chosen) without producing any hand-resolvable merge conflict on the shared file.
- [ ] AC-2: Running PRD-549 (9 siblings touching `builtins/__init__.py`) end-to-end produces zero hand-resolved merge conflicts.
- [ ] AC-3: Running PRD-556 (18 siblings touching `cli/__init__.py`) end-to-end produces zero hand-resolved merge conflicts.
- [ ] AC-4: A test fixture with two ready siblings that declare overlapping impacts exercises the chosen ordering mechanism directly (unit test).
- [ ] AC-5: The executor's decision is visible to the user — log line or JSON event explaining why a sibling was deferred.
- [ ] AC-6: An explicit `depends_on:` edge between two siblings always wins over auto-inferred ordering (no double-serialization, no silent override).

## References

- Current incident: PRD-549 children during 2026-04-09 execution (laborious sibling rebases).
- [[PRD-220-graph-execution]] — the executor that would enforce ordering.
- [[PRD-545-harness-driven-rebase-and-conflict-resolution]] — overlapping scope (Option 5).
- [[PRD-546-impact-declaration-drift-detection]] — shares file-overlap computation.
- [[PRD-549-builtins-package-split]] — concrete example with 9-way fan-out.
- [[PRD-550-upstream-impact-propagation]] — complementary (reactive vs proactive).
- [[PRD-551-parallel-graph-execution]] — future parallel executor that needs to cooperate with this.
- [[PRD-552-merge-upstream-task]] — handles the multi-dep case which this PRD doesn't.
- [[PRD-556-modularize-cli]] — 18-way fan-out, next victim of the pattern.
- [[PRD-557-modularize-runner]] — 4-way fan-out, also affected.
- `src/darkfactory/impacts.py` — existing overlap-detection helper.

## Assessment (2026-04-11)

- **Value**: 4/5 — this is the MVP that unblocks future N-way fan-outs
  (PRD-556's 18 children already exposed the pain, any future
  modularization will hit it again). The scheduler's "parallel siblings
  collide on rebase" bug is the single most consistent source of
  laboriously-hand-resolved conflicts. Even just shipping Option 1 buys
  relief for every epic with a shared file.
- **Effort**: m — the infrastructure already exists. `impacts.py` has
  `impacts_overlap()`, `prd validate` already warns on sibling overlap,
  PRD-220's executor already supports single-dep stacking. Option 1
  (phantom `depends_on` at scheduling time) is a scheduler patch, not
  a new subsystem.
- **Current state**: scaffolded. `impacts.py` + the validate warning
  are the plumbing. The executor in `graph_execution.py` does not yet
  consult overlaps when picking the next sibling.
- **Gaps to fully implement (Option 1 MVP)**:
  - Extend `graph_execution.py` candidate selection: when multiple
    sibling PRDs under the same parent are `ready`, compute
    `impacts_overlap()` pairwise and order them by `(priority_rank, number)`
    among overlapping siblings so later siblings wait.
  - Emit a scheduling event line explaining why a sibling was deferred
    (per AC-5). Reuse the existing `RunEvent` or extend to a new event
    type.
  - `prd run --no-auto-serialize` escape hatch flag (per the open
    question).
  - Tests: two-sibling overlap → serialized; three siblings where
    only two overlap → the odd one out runs in parallel (once PRD-551
    exists) or first (sequential).
- **Recommendation**: do-next — schedule immediately after the next
  fan-out epic is planned. Skip Options 2–6 entirely for now; revisit
  only if Option 1 produces noticeable false-positives. Bind this PRD's
  Option-1 scope into a single PR instead of waiting for the broader
  PRD-545 cluster to be re-planned.
