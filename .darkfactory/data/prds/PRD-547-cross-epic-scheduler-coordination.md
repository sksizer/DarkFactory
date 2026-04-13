---
id: PRD-547
title: Cross-epic scheduler coordination — coordinate parallel runs across multiple epics
kind: feature
status: draft
priority: low
effort: l
capability: complex
parent:
depends_on:
  - "[[PRD-545-harness-driven-rebase-and-conflict-resolution]]"
blocks: []
impacts:
  - src/darkfactory/scheduler.py
  - src/darkfactory/runner.py
  - src/darkfactory/state.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - scheduler
  - concurrency
  - feature
---

# Cross-epic scheduler coordination — coordinate parallel runs across multiple epics

## Summary

PRD-545 introduces a per-epic scheduler that uses `impacts:` overlap to sequence sibling children within a single epic. Explicitly out of scope for that PRD: **two different epics running simultaneously whose children touch overlapping files.** This PRD addresses that gap. When more than one epic is in flight at the same time, the harness must consider conflicts across *all* in-flight PRDs from *all* epics, not just within each epic in isolation.

## Motivation

### The gap

PRD-545's v1 scheduler reasons about one epic's children at a time. If you run `prd run epic-A` in one terminal and `prd run epic-B` in another, each scheduler builds its own conflict graph independently and they have no shared view. Two children — one from each epic — can be queued simultaneously, both touch `src/darkfactory/runner.py`, and the harness produces two branches that conflict at merge time exactly the way PRD-545 was supposed to prevent.

### Why this is a real-world concern, not a theoretical one

- The whole pitch of the harness is "decompose work into many small parallel pieces." As a project matures and multiple developers (or multiple agent sessions) drive the harness, simultaneous epics become normal, not exceptional.
- Even within a single user's workflow, "I'll start the long-running refactor epic and pick at this small bug-fix epic in the meantime" is a perfectly reasonable usage pattern that today produces silent collisions.
- Cross-epic conflicts have *worse* failure modes than intra-epic ones because there's no shared `_legacy.py` workaround available — the two epics have no way of knowing about each other's existence at PRD-authoring time.

### Why this is a separate PRD from PRD-545

Three reasons:

1. **Implementation cost.** Cross-epic coordination needs a global lock or a shared state store; intra-epic scheduling doesn't. Lumping them together would inflate PRD-545's scope past the point where it could ship in a reasonable time.
2. **Adoption risk.** Cross-epic coordination is the kind of feature that needs careful rollout — it's the difference between "the harness sometimes won't start the epic you asked for" (acceptable) and "the harness deadlocks waiting for a lock that never resolves" (not acceptable). Better to bed in PRD-545's per-epic case first, then layer this on with confidence.
3. **Validation pathway.** PRD-545 has a concrete end-to-end integration test (re-running PRD-549's nine parallel children). This PRD's validation requires running two epics concurrently and observing that they sequence correctly — a different test harness, larger setup, and not blocked by the initial implementation.

## Requirements

### Functional

1. **Global in-flight registry.** The harness maintains a single registry of all currently-in-flight PRDs (across epics, across user sessions on the same machine, across worktrees of the same project). Records: PRD ID, current state, declared `impacts:` set, owning epic (if any), starting commit.
2. **Conflict-aware admission control.** When `prd run <PRD>` is invoked, the scheduler checks the global registry: if the new PRD's effective impact set intersects with any in-flight PRD's effective impact set, the new PRD is **queued** (not started) until the conflicting in-flight PRD finishes.
3. **Queued PRDs are visible.** `prd status` shows queued PRDs with the reason ("waiting for PRD-X to finish; overlaps on src/foo.py") and the chain of upstream blockers if multiple.
4. **Respect epic boundaries when possible.** Within a single epic, intra-epic ordering (PRD-545) takes precedence — the global registry just *also* checks against PRDs from *other* epics. Children of the same epic don't double-block each other.
5. **No deadlocks.** Because the registry is acyclic by construction (queued items only wait for in-flight items, not vice versa), deadlock is not possible. But the implementation must explicitly assert this with a runtime check that errors if a cycle ever forms (defensive programming against bugs).
6. **Stale-entry detection.** If an in-flight entry has been "running" for far longer than expected (e.g. its agent process is dead, the harness was killed), the registry must time it out and mark it abandoned, freeing whatever was queued behind it. Configurable timeout, default 24h.
7. **Manual override.** `prd run --no-coordination <PRD>` bypasses the global registry entirely and starts immediately. Documented as "use only if you know what you're doing." Logs a loud warning.
8. **`prd queue`** subcommand: lists queued PRDs and their wait reasons. `prd queue --kick` retries blocked queue items immediately (in case the registry is stale).
9. **Cross-machine vs same-machine.** v1 scope is **same-machine only** — registry lives on local disk under `.darkfactory/registry.json`. Cross-developer coordination (via a shared remote) is a follow-up.

### Non-functional

1. **Atomic.** Registry updates use file locking or an equivalent atomic mechanism. No torn writes when two `prd run` invocations race.
2. **Cheap to read.** `prd status` reads the registry on every invocation; must be sub-100ms even with hundreds of historical entries.
3. **Recoverable.** If the registry file is corrupted or deleted, the harness logs a warning, treats the registry as empty, and continues — corrupted coordination state must not brick the tool.
4. **Observable.** Every queue/dequeue/timeout/admission event is logged. A user investigating "why is my run waiting?" should find the answer in one place.

## Technical Approach

- **`src/darkfactory/registry.py`** (new) exposing:
  - `register(prd, impacts, epic) -> RegistryEntry` — atomic insert if no conflicts; raises `WouldConflict(blockers)` otherwise.
  - `release(entry)` — called on PRD completion/failure.
  - `query(prd_id) -> RegistryEntry | None`.
  - `list_in_flight() -> list[RegistryEntry]`.
  - `gc_stale(timeout)` — purge stale entries.
- Backed by `.darkfactory/registry.json` with file locking via `fcntl.flock` (POSIX) or equivalent. Atomic write via temp-file-rename.
- Hooks into `runner.run_epic` and `runner.run_prd` from PRD-545: each spawn calls `register()` first; each finish calls `release()`.
- Re-uses the conflict-graph computation from PRD-545 — the algorithm doesn't change, only the input set widens from "this epic's children" to "this epic's children plus all in-flight PRDs from the registry."

## Acceptance Criteria

- [ ] **AC-1:** Two `prd run` invocations against PRDs with overlapping declared `impacts:` started simultaneously result in one running and one queued. The queued one starts automatically when the first finishes.
- [ ] **AC-2:** `prd status` shows the queued PRD with a clear "waiting for PRD-X (overlaps on src/foo.py)" reason.
- [ ] **AC-3:** Two `prd run` invocations against PRDs with non-overlapping `impacts:` both start immediately and run in parallel.
- [ ] **AC-4:** Killing a running PRD's harness process (SIGKILL the parent) eventually releases its registry entry via the stale-entry timeout (24h default, configurable to 1m for tests).
- [ ] **AC-5:** A corrupted `.darkfactory/registry.json` causes a logged warning and is treated as empty; the harness continues operating.
- [ ] **AC-6:** `prd run --no-coordination` skips the registry entirely and runs immediately, logging a loud warning.
- [ ] **AC-7:** `prd queue` lists all currently-queued PRDs with their blockers.
- [ ] **AC-8:** Within an epic spawned via `prd run <epic>`, the epic's own scheduler (PRD-545) and the global registry agree: an epic child is queued by the global registry only if it conflicts with something *outside* the epic; otherwise the per-epic scheduler handles it.
- [ ] **AC-9:** The registry never deadlocks. A defensive runtime check asserts acyclicity and errors loudly if a cycle is ever created.
- [ ] **AC-10:** Two concurrent `prd run` invocations on PRDs that conflict do not produce a torn registry write. Verified via a stress test running 10 parallel `prd run` invocations on a mix of conflicting and non-conflicting PRDs.

## Open Questions

- [ ] **Same-machine vs cross-developer.** v1 is same-machine. A team using darkfactory collaboratively will eventually want a shared registry (Redis? a small server? a file in a shared S3 bucket?). Defer until the same-machine case has shipped and we know the access patterns.
- [ ] **CI integration.** Should CI runners participate in the registry, or is the registry strictly for interactive `prd run`? Leaning toward "interactive only" — CI typically operates on a single PRD per job and doesn't need coordination — but worth confirming.
- [ ] **Queue ordering.** When multiple PRDs are queued behind the same blocker, what order do they unblock in? FIFO is the obvious answer; priority field (`priority: high|medium|low`) is the next obvious refinement. Recommendation: FIFO in v1, priority-aware in v2.
- [ ] **Visibility into the registry from other tools.** The registry is plaintext JSON, so anything can read it. Should there be a `--json` mode on `prd queue` and `prd status` to make scripted integration trivial? Probably yes.
- [ ] **Per-project vs per-machine registry.** Currently scoped per-project (`.darkfactory/registry.json` lives in each target project). What if a developer runs PRDs across two projects that share files (e.g. a monorepo split into separate `.darkfactory/` roots)? Out of scope for v1; flag as a known limitation.
- [ ] **Drift integration.** PRD-546 adds drift detection. Should the global registry use drift-augmented effective impacts (per PRD-546 AC-11) when computing cross-epic conflicts? Yes, almost certainly — same answer as inside the per-epic case.

## References

- [[PRD-545-harness-driven-rebase-and-conflict-resolution]] — the per-epic scheduler this PRD generalizes to global scope. Hard dependency.
- [[PRD-546-impact-declaration-drift-detection]] — the source of truth for "effective impacts" that this PRD's registry consults. Soft dependency; both can ship in either order, but they're better together.
- `src/darkfactory/impacts.py` and `src/darkfactory/containment.py` — the underlying primitives.

## Assessment (2026-04-11)

- **Value**: 2/5 today — the "two epics running simultaneously" scenario
  this guards against doesn't happen in the current single-developer
  usage pattern. It's a real concern for a team setting, but this is not
  a team product today. Rises to 4/5 in a multi-developer world.
- **Effort**: l — new `registry.py` module, atomic file locking, state
  persistence, stale-entry GC, a `prd queue` subcommand, plus hooks
  into every `runner.run_epic` / `runner.run_prd` entry.
- **Current state**: greenfield. Nothing from this PRD exists.
- **Gaps to fully implement**: all of it — new module, new CLI command,
  new file format, new atomic-write discipline, new runner hooks.
- **Recommendation**: defer — do not schedule until (a) PRD-545 Phase 1
  lands and (b) there's actual concurrent usage driving the need.
  Keep as a reference design for when the team case becomes real.
  Hard dep on PRD-545 makes this a natural follow-up, not a standalone.
