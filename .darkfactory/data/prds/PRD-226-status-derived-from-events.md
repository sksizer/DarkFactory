---
id: "PRD-226"
title: "Derive PRD status from event log + git history (eliminate drift architecturally)"
kind: epic
status: draft
priority: medium
effort: l
capability: complex
parent: null
depends_on: []
blocks: []
impacts: []  # epic — children declare their own
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-11'
tags:
  - harness
  - architecture
  - state
---

# Derive PRD status from event log + git history

## Summary

Today PRD `status:` is a mutable field in YAML frontmatter. The harness writes to it, the agent writes to it, humans edit it directly. Every write is an opportunity for drift between "what the field says" and "what's actually true". We've already shipped:

- **PRD-213** to fix one drift mode (set_status writing to the source repo instead of the worktree)
- **PRD-214** to fix another (yaml round-trip mangling other fields)
- **PRD-215** to prevent two runners from colliding on the same PRD
- **PRD-217** to prevent two runners from racing on the same worktree
- **PRD-218** to make agent runs visible so we can spot weirdness
- **PRD-224** to add 7 different invariants that catch drift after the fact

That's a lot of patches for one design choice. The alternative — **status is not a field, it's a computed view** — eliminates the entire class of bugs because there is nothing mutable to drift.

This PRD captures that direction as a future architectural change. It is **not a near-term task** — most of PRD-224 has to land first to make this possible — but it's worth tracking so the design doesn't get reinvented later.

## Motivation

### What "status as a field" costs us today

| Cost | Detail |
|---|---|
| 7+ PRDs of patches | 213, 214, 215, 217, 218, 224, 225, 226 — every drift mode needs its own fix |
| Manual reconciliation | PR #18 had to flip 4 PRDs by hand because the harness left them stale |
| Lost trust | An AI assistant (or human) can't trust `status: review` without cross-checking git |
| GH Action complexity | PRD-224.5 needs a whole CI job just to mirror local state |
| Race conditions | The status field is a single mutable cell — every concurrency bug in the harness routes through it |
| Confusing semantics | "Done in main" vs "done on a branch" vs "done with status review" — three different things |

### What "status as derived" gives us

A **single source of truth** computed from observable facts:

```python
def compute_status(prd: PRD, git: GitState, gh: GitHubState) -> Status:
    # Architectural status is fully derived from observable state.
    if prd.spec.is_draft_marker_present:
        return "draft"
    if not prd.spec.has_ready_marker:
        return "draft"
    if any(commit_for_prd(prd) in branch for branch in git.branches):
        if pr_for_branch(branch) is None:
            return "in-progress"
        if pr.state == "open":
            return "review"
        if pr.state == "merged":
            return "done"
        if pr.state == "closed":
            return "cancelled"
    if any(commit_for_prd(prd) in main_log):
        return "done"
    return "ready"
```

The function reads the world; it doesn't write to anything. **There's nothing to drift.**

## What stays in the markdown file

The user noted in the design conversation: even with derived status, **some signals still need to be authored**. The markdown file is the right place for those:

- **`draft` ↔ `ready` boundary**: needs an explicit "I'm done writing this PRD, it's ready to work" signal. Could be a YAML field (`ready_at: 2026-04-08`), or a Markdown frontmatter flag (`ready: true`), or an absence of a `draft:` marker, or a commit that flips it. Whichever we pick, this signal IS authored — it's not derived.
- **`cancelled` rationale**: when a PRD is cancelled, the file should explain why. Hard to derive that from git.
- **Spec content**: requirements, ACs, technical approach — these are authored, not state.

So the markdown file becomes:
- **Spec** (mostly unchanged — requirements, ACs, etc.)
- **Lifecycle markers** that need authoring (`ready`, `cancelled`, etc.)
- **Metadata** that humans set (parent, depends_on, blocks, tags, capability, effort)

Everything that's currently a `status:` field becomes a property of the computed view.

## Design sketch

### Source of truth

| Today | After this PRD |
|---|---|
| `.darkfactory/data/prds/PRD-X.md` frontmatter has `status:` | `.darkfactory/data/prds/PRD-X.md` has `ready:`, `cancelled_reason:` (sometimes); status is derived |
| `prd status` reads frontmatter | `prd status` queries git + gh + reads frontmatter, derives a status per PRD |
| `set_status` builtin mutates the file | `set_status` builtin is removed entirely |
| Status drift is possible | Status drift is **architecturally impossible** — there's nothing to drift |

### Event log (optional)

Could go further: add a structured event log at `.darkfactory/data/events/PRD-X.jsonl` that the harness appends to as things happen:

```jsonl
{"ts":"2026-04-08T10:00Z","type":"created","actor":"sksizer"}
{"ts":"2026-04-08T11:00Z","type":"ready","actor":"sksizer"}
{"ts":"2026-04-08T12:00Z","type":"run_started","actor":"harness","branch":"prd/PRD-X-foo"}
{"ts":"2026-04-08T12:30Z","type":"pr_opened","number":42}
{"ts":"2026-04-08T13:00Z","type":"merged","sha":"abc123"}
```

Status is then: "look at the latest event in the log". The log is append-only, so it's git-friendly and can't drift either. But it adds a layer of state, so it's not strictly necessary if git history + frontmatter is enough.

### Migration

Migrating from "status field" to "derived status" is non-trivial but tractable:

1. **Phase 1**: dual-source. Keep the `status:` field but add a derived computation; `prd validate` warns when they disagree.
2. **Phase 2**: derived is canonical. The field becomes a cache that the harness updates from the derived value. Drift warnings become hard errors.
3. **Phase 3**: drop the field entirely. Replace with `ready:` and `cancelled_reason:` markers as needed.

Each phase is its own PRD; users can opt out of phase 3 if they prefer the field-based view.

## Decomposition (rough — to be detailed when this becomes ready)

- **PRD-226.1** — Define the derivation function: pure Python, takes `(PRD, GitState, GitHubState)`, returns `Status`. Tested in isolation.
- **PRD-226.2** — Add `prd status --derived` flag that uses the derivation function instead of reading the field. Side-by-side with the existing path so users can compare.
- **PRD-226.3** — Phase 1 dual-source: validate warns on field/derived mismatch; harness writes to both
- **PRD-226.4** — Phase 2: derived is canonical, field is a cache
- **PRD-226.5** — Phase 3: remove the field; add `ready:` marker
- **PRD-226.6** — Optional: structured event log at `.darkfactory/events/`

## Why this is `status: draft` and not `ready`

Three reasons:

1. **PRD-224 has to land first.** This PRD is the "do it right" alternative to the patches in PRD-224. Until 224 ships, we still need the patch-based fixes — and seeing how well they work informs whether the architectural shift is worth it.
2. **Migration cost is real.** Every other tool / IDE / CI integration that currently reads the `status:` field would need updating. We need to know what depends on it before we move it.
3. **Some uncertainty about the right derivation rules.** The function above is a sketch — corner cases like "branch deleted but commit still on main" or "PR closed without merge" need real-world validation.

The right time to revisit this is **after PRD-224 has been in use for a few weeks** and we have a clear picture of which drift modes the patches catch and which they don't.

## Acceptance Criteria (rough — refine when ready)

- [ ] AC-1: A pure function `compute_status(prd, git, gh) -> Status` exists and is unit-testable
- [ ] AC-2: `prd status --derived` returns a value for every PRD without errors
- [ ] AC-3: Side-by-side comparison shows field-vs-derived agreement on 100% of PRDs in a clean repo
- [ ] AC-4: Drift detection: a deliberately-stale field triggers a warning under phase 1
- [ ] AC-5: Phase 3: removing the field doesn't break any read site
- [ ] AC-6: Migration runs cleanly on darkfactory itself

## Open Questions

- [ ] Does the derivation function need to handle force-pushed branches? Probably yes — match against commit content rather than branch name where possible
- [ ] How does derived status interact with offline mode? The function needs `gh` for some states; offline runs would have to fall back to "unknown" for those
- [ ] Are there derivation rules where reasonable people would disagree? E.g. "PR open but the author hasn't pushed in 30 days" — review or stale-review? Recommendation: don't model nuance, keep states discrete
- [ ] What about the existing PRD-541 (color in `prd status`)? The color rules would need to read from derived states — minor refactor

## Relationship to other PRDs

- **PRD-224** — does the patch-based fixes that make today's field-based status livable; this PRD is the architectural alternative
- **PRD-213, 214, 215, 217, 218, 225** — all motivated by problems that don't exist in a derived-state world
- **PRD-223 reconcile-status operation** — partially obsoleted by this PRD: if status is derived there's nothing to reconcile
- **PRD-222 `.darkfactory/`** — provides the layout for the optional event log

## Assessment (2026-04-11)

- **Value**: 2/5 today (rising to 4/5 only if drift becomes a recurring
  problem). The PRD author explicitly says this is "not a near-term
  task" and that PRD-224's patch-based fixes need to "be in use for a
  few weeks" before revisiting. PRD-224 is now landed. The honest
  follow-up is "have we seen drift since?" and the answer today is
  "rarely, and never painfully."
- **Effort**: xl — this is an architectural migration, not a task.
  Three phases, field rename, removal of the `set_status` builtin,
  update of every read site, migration of every tool/CI integration
  that currently reads the `status:` field.
- **Current state**: greenfield. No derivation function, no
  `--derived` flag, no phase-1 dual-source wiring.
- **Gaps to fully implement**: everything in the PRD body.
- **Recommendation**: defer — do not schedule. Re-score in one quarter
  (2026-07 or later). If by then the drift patches are still
  sufficient, close this PRD as "deliberately not pursued." The
  cost of the migration is real and the pain it solves is currently
  hypothetical. Keep the PRD as a design artifact in case the
  situation changes.
