---
id: PRD-545
title: Harness-driven rebase and conflict resolution for parallel epic children
kind: feature
status: draft
priority: medium
effort: l
capability: complex
parent:
depends_on: []
blocks:
  - "[[PRD-549-builtins-package-split]]"
impacts:
  - src/darkfactory/runner.py
  - src/darkfactory/impacts.py
  - src/darkfactory/builtins/**
  - src/darkfactory/cli/**
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-11'
tags:
  - harness
  - scheduler
  - reliability
  - dag
---

# Harness-driven rebase and conflict resolution for parallel epic children

## Summary

When an epic decomposes into N sibling child PRDs that are intended to run in parallel, and two or more of those siblings touch the same file, the harness today produces N independent branches that each cleanly apply against `main` in isolation but conflict pairwise with each other at merge time. There is no runner-level machinery for:

- **Detecting the conflict *before* attempting to merge** (so the scheduler can sequence the work rather than letting humans discover it after the fact).
- **Rebasing a sibling onto the merged result of an earlier sibling and re-verifying** (tests, lint, typecheck still pass).
- **Invoking an agent to resolve a non-trivial conflict** with full context about what was expected and why.
- **Reporting the state of a partially-merged epic** so a human knows which siblings landed, which are blocked on conflicts, and which are still pending.

This PRD proposes adding those capabilities so that genuine parallel fan-out from an epic is a first-class workflow rather than a foot-gun.

## Motivation

### The concrete incident (forthcoming)

PRD-549 (splitting `builtins.py` into per-function submodules) was originally designed as a nine-child parallel fan-out explicitly to stress-test the harness's DAG execution. An audit during PRD-549's refinement discovered that the harness has **no post-hoc rebase or merge-conflict resolution machinery**: `runner.py` contains zero references to rebase or merge, and `impacts.py` / the `prd conflicts` CLI command performs only *static pre-execution* impact-overlap detection from `impacts:` frontmatter globs. The output of `prd conflicts` is a warning printed at run time. Nothing acts on it.

As a result, PRD-549 had to be redesigned to *avoid* the conflict — by pre-relocating `builtins.py` into a transitional `_legacy.py` bucket so each child only makes a one-line delete in the shared file. That's a fine workaround for one epic, but it's not a general solution. The next epic with a true file-level fan-out will hit the same wall and require its own custom workaround. The right fix is in the harness itself.

### Why parallel fan-out matters

Parallel execution of sibling children is one of the main value propositions of an automated workflow harness:

- **Throughput.** Nine independent refactors in the time it takes to do one.
- **Isolation.** Each child is its own worktree, its own agent run, its own test cycle. If child #4 breaks, children #1–3 and #5–9 are unaffected.
- **Matches how humans split work.** "Decompose the epic into N parallel pieces" is the whole point of epics.

But the value evaporates the moment those siblings touch overlapping files, because the harness doesn't know how to reconcile them. Today the options are:

- **(a)** Serialize everything (defeats the point of parallelism).
- **(b)** Hand-design the epic so siblings can't conflict (works sometimes, as in PRD-549's `_legacy.py` trick, but it's brittle and requires specific foreknowledge).
- **(c)** Let the humans clean up afterwards (defeats the point of automation).

None of those are satisfying. The harness should handle at least the common cases automatically.

### What already exists and can be built on

- **`impacts.py` / `find_conflicts()` / `effective_impacts()`** — walks containment tree, applies glob intersection, exempts parent/child pairs. Produces a list of `(other_prd, overlapping_files)` tuples. This is the right substrate for a scheduler to reason about conflict risk *before* execution.
- **`containment.py`** — gives us the epic → children relationship directly from frontmatter.
- **`runner.py`** — already knows how to spawn a worktree, run an agent, commit, push, open a PR. Adding a "rebase this worktree onto a newer base" operation is incremental.
- **`prd conflicts <ID>`** — the pre-execution check already exists; it just needs to be consulted by the scheduler, not merely displayed to the user.

## Requirements

### Phase 1 — Pre-execution conflict detection drives scheduling

1. When the harness is asked to execute an epic (or any set of PRDs), it must query `find_conflicts()` to build a **conflict graph** over the candidate PRDs: nodes are PRDs, edges connect any pair that would overlap on at least one file.
2. From that graph, compute an execution schedule that maximizes parallelism while avoiding concurrent execution of conflicting pairs. Concretely: any two PRDs connected by an edge must run **sequentially**, in some ordering; unconnected PRDs may run **in parallel**.
3. The ordering within a conflicting group may be user-declared (via `depends_on` frontmatter) or, if unspecified, chosen by a simple deterministic policy (e.g. lexicographic on PRD ID). Flagged for Open Question discussion.
4. The scheduler must log its chosen plan **before** starting any work: "Will execute PRD-A, PRD-C, PRD-E in parallel. Then PRD-B (depends on A via file overlap). Then PRD-D (depends on C via file overlap)."
5. `prd run --dry-run <epic>` must print this plan without executing anything so users can inspect it.
6. If two PRDs overlap only on the PRD file itself (e.g. both set their own status), that is not a real conflict — status commits and PR commits are serialized by the harness already and can be filtered out of the overlap set.

### Phase 2 — Post-merge rebase of dependent siblings

1. When the scheduler finishes the first PRD in a conflicting group, it must rebase each remaining sibling in that group onto the new `main` **before** running the agent.
2. Rebase strategy:
   - **Trivial case (git auto-rebase succeeds):** run `just test`, `just lint`, `just typecheck`, `just format-check` on the rebased worktree. If all pass, the sibling is ready to proceed; its agent does not need to re-run.
   - **Non-trivial case (git rebase produces conflicts):** fall through to Phase 3.
3. After a successful rebase, the sibling's PR is force-pushed (with lease) to update the branch. The PR description is updated with a note: "Rebased onto <new sha> at <timestamp> after PRD-X merged."
4. If the rebased sibling's tests fail for reasons other than conflicts (e.g. the earlier PRD changed a shared contract), the harness must detect this and fall through to Phase 3 as if it were a conflict — "the merged result broke this sibling" is morally the same problem as a merge conflict, just surfaced by tests instead of git.
5. Rebases happen in the scheduler's declared order. Siblings still waiting on earlier rebases remain in a `pending-rebase` state.

### Phase 3 — Agent-driven conflict resolution

1. When git rebase produces conflicts OR when a clean rebase produces failing tests, the harness spawns a **conflict-resolution agent** on the sibling's worktree with:
   - The conflict markers (or failing test output).
   - The original sibling PRD's goal statement and acceptance criteria.
   - The earlier sibling's diff (the one that introduced the conflict) and its PRD.
   - The explicit instruction: "Preserve the intent of both changes. Do not silently drop work from either side. If the two are fundamentally incompatible, stop and report — do not guess."
2. The agent resolves the conflict, runs the test/lint/typecheck loop, and if green, commits with a message like `chore(rebase): resolve conflict with PRD-X (merged into main)`.
3. If the agent cannot resolve (hits its turn limit, decides the two changes are fundamentally incompatible, or produces still-failing tests after three tries), the harness marks the sibling as **blocked** with a clear human-readable reason and moves on. It does not drop the sibling on the floor.
4. The conflict-resolution agent has a separate timeout budget from the original implementation agent — it's a narrower task and should not inherit an already-burned-down clock.
5. Agent invocations during conflict resolution are logged as clearly as original runs, with their own section in the harness output log so a human reviewing afterwards can see exactly what the resolver was told and what it did.

### Phase 4 — Reporting and state management

1. `prd status` must show, for each PRD in an in-flight epic, its current state: `pending`, `running`, `pending-rebase`, `rebasing`, `resolving-conflict`, `ready`, `merged`, `blocked`.
2. When a sibling is `blocked` on conflict resolution, the output names the conflicting sibling and either the conflict file list or the failing test name.
3. An epic-level rollup shows "N of M children merged, K blocked, L pending" with the blocking reasons.
4. Crash recovery: if the harness is killed mid-epic, restarting it must correctly resume the in-flight state — already-merged children stay merged, in-progress rebases can be retried, the scheduler picks up where it left off. State lives in the existing `.darkfactory/state.json` (or its equivalent), not in-memory only.

### Non-functional requirements

1. **Determinism.** Same epic, same starting commit, same conflict pattern → same execution plan. No hidden randomness.
2. **Observability.** Every scheduling decision, rebase attempt, and conflict-resolution agent invocation is logged in one place. A human debugging a stuck epic should find the full story in one file.
3. **Opt-out.** `prd run <epic> --no-auto-rebase` falls back to today's behavior (produce independent branches, let humans sort it out) for users who prefer that. Default is the new behavior.
4. **Don't rewrite merged history.** Never force-push anything that has already merged into `main`. Force-push is only allowed against a sibling's own feature branch that has not yet been merged.
5. **Bounded retries.** Conflict-resolution agent is capped at 3 tries per conflict. Repeated failure marks the sibling blocked. No infinite loops.

## Technical Approach

### Module sketch

- **`src/darkfactory/scheduler.py`** (new) — consumes `impacts.find_conflicts()` output + `depends_on` edges, produces a DAG, yields execution waves. Pure function of PRD metadata; no side effects.
- **`src/darkfactory/rebase.py`** (new) — wraps git rebase, detects conflicts, runs post-rebase verification (`just test` etc.), returns a structured result (`Rebased` | `ConflictsDetected(files)` | `TestsFailed(output)`).
- **`src/darkfactory/runner.py`** — gains a top-level `run_epic(epic)` entry point that invokes the scheduler, walks the waves, and dispatches to rebase and conflict resolution as needed.
- **`src/darkfactory/workflows/resolve_conflict/`** (new built-in workflow) — the workflow that the conflict-resolution agent runs. Defines its own role, prompts, and verification step. Reuses the existing agent invocation machinery.
- **`src/darkfactory/state.py`** — extended to track per-PRD execution state across harness invocations.

### Integration with existing `impacts` system

The `impacts:` frontmatter globs are already the source of truth for conflict *prediction*. This PRD makes the scheduler *act on* those predictions rather than just printing them. If a PRD's declared impacts are wrong (it touches files it didn't declare), the scheduler will underestimate conflicts. That's a separate problem — accurate impact declaration is already enforced by review; this PRD doesn't try to infer impacts from code.

A follow-up could run a "declared vs actual impacts" check after each PRD merges and warn when they diverge, but that's out of scope here.

### Integration with `depends_on`

`depends_on` frontmatter is already used for explicit ordering. This PRD extends its semantics:

- **Explicit `depends_on`** — hard edge in the DAG. Child must wait for parent.
- **Inferred from `impacts` overlap** — soft edge. Introduces a scheduling constraint but does not imply a semantic dependency. The distinction matters for how the plan is displayed ("PRD-B waits for PRD-A because it touches overlapping files", vs "PRD-B waits for PRD-A because PRD-B's frontmatter says so").

## Acceptance Criteria

- [ ] **AC-1 (Phase 1):** `prd run <epic> --dry-run` prints an execution plan for the epic that groups siblings into parallel waves separated by inferred dependencies from `impacts` overlap. Unconnected siblings land in the same wave. Conflicting siblings land in sequential waves.
- [ ] **AC-2 (Phase 1):** The plan logs *why* each sequencing edge exists: `depends_on`, `impacts` overlap (naming the files), or containment.
- [ ] **AC-3 (Phase 2):** When the first sibling in a conflicting group merges, the harness automatically rebases every remaining sibling in the same group onto the new `main`, runs the full verification suite on each, and reports status. Clean rebases require no agent work.
- [ ] **AC-4 (Phase 2):** Force-pushes after rebase use `--force-with-lease` and never target `main` or any already-merged branch.
- [ ] **AC-5 (Phase 3):** When a rebase produces conflicts or post-rebase tests fail, the harness spawns a conflict-resolution agent with the conflict context, the goals of both colliding PRDs, and the prompt instruction to preserve both intents. The agent's work is logged in a distinct section of the harness output.
- [ ] **AC-6 (Phase 3):** A conflict-resolution agent that cannot resolve after N attempts (default 3) marks the sibling `blocked` with a human-readable reason and does not dequeue its siblings — other non-conflicting work continues.
- [ ] **AC-7 (Phase 4):** `prd status` shows per-PRD state (`pending`, `running`, `pending-rebase`, `rebasing`, `resolving-conflict`, `ready`, `merged`, `blocked`) for every PRD in an in-flight epic, and an epic-level rollup of "N of M merged, K blocked".
- [ ] **AC-8 (Phase 4):** Killing and restarting the harness mid-epic resumes correctly: already-merged children stay merged, in-flight rebases are retried, blocked children stay blocked until manually cleared, and no work is duplicated.
- [ ] **AC-9 (non-functional):** Same epic, same starting commit, same conflict pattern → same execution plan twice in a row.
- [ ] **AC-10 (opt-out):** `prd run <epic> --no-auto-rebase` produces today's behavior (independent branches, no scheduler, no auto-rebase, no conflict-resolution agent).
- [ ] **AC-11 (regression):** Non-epic single-PRD runs continue to behave exactly as they do today. This feature adds machinery for epics without touching the simple case.
- [ ] **AC-12 (validation):** PRD-549's original nine-parallel-children design (without the `_legacy.py` workaround) is re-runnable under this feature as an end-to-end integration test and completes successfully with all nine children merged.

## Open Questions

- [ ] **Default ordering within a conflicting group.** When two sibling PRDs conflict and neither has a `depends_on` edge, how do we pick which goes first? Proposals: (a) lexicographic PRD ID, (b) smaller `effort` first (fail fast on trivial work), (c) larger `effort` first (the big one dictates the shape, smaller ones adapt), (d) require the user to disambiguate via `depends_on` and fail the scheduler otherwise. Leaning toward (d) — force explicit intent, fail loud.
- [ ] **Conflict-resolution agent model.** Should it always be the same model tier as the original implementation agent, or a fixed "strong" model (e.g. Opus) since conflict resolution is higher-stakes? Leaning toward fixed strong model — conflicts are rare, cost is bounded, quality matters.
- [ ] **Agent retry budget.** Default to 3 conflict-resolution attempts per sibling. Configurable? Per-epic? Global?
- [ ] **Blocking policy.** When a sibling is `blocked`, should downstream work (siblings that don't conflict with the blocked one) continue? Yes, probably. But what about siblings that conflict with the *blocked* one — they can't rebase, so they're transitively blocked too. How deep does this cascade and how do we report it cleanly?
- [ ] **Cross-epic conflicts.** Two different epics running simultaneously whose children happen to overlap. Out of scope for the first version? Leaning yes — ship the single-epic case first, worry about cross-epic coordination later.
- [ ] **Impact declaration drift.** If a PRD's actual diff touches files it didn't declare in `impacts:`, the scheduler will underestimate conflicts and siblings will collide unexpectedly at rebase time. Separate follow-up PRD: post-merge check that warns when declared `impacts` diverge from actual diff.
- [ ] **Worktree cleanup semantics.** When a sibling is blocked, do we keep its worktree around for manual inspection? For how long? Today worktrees are cleaned by `cleanup_worktree` after a successful PR; blocked ones need a separate policy.
- [ ] **Interactive mode.** Should there be a `prd resolve <PRD>` command that lets a human pick up a blocked sibling, resolve it manually (with harness help), and hand it back to the scheduler? Nice-to-have; probably a follow-up.

## References

- Prior art: `src/darkfactory/impacts.py` — the static conflict detector this PRD builds on.
- Prior art: `src/darkfactory/containment.py` — parent/child relationships.
- Prior art: `prd conflicts <ID>` CLI command in `src/darkfactory/cli/conflicts.py`.
- Originating incident: [[PRD-549-builtins-package-split]] — the epic whose nine-parallel-children design exposed this gap. AC-12 of this PRD explicitly targets re-running that design without the `_legacy.py` workaround.
- [[PRD-543-harness-pr-creation-hardening]] — overlaps in spirit: both are "the harness needs to surface and act on information it already has."
