# Value vs. Effort assessment rubric (2026-04-11)

The value/effort pass over every non-closed PRD uses the scales below. The
per-PRD writeup lives inside each PRD's `## Assessment (2026-04-11)` section.
The top-level summary is `SUMMARY.md` in this directory.

## Value (1–5)

Forward-looking user/project impact, not "hours of work done."

| Score | Meaning |
|-------|---------|
| **5** | Unblocks a broken workflow, prevents data loss, or turns a manual recurring task into an automatic one. Measurable pain goes away. |
| **4** | Removes real friction that hits every session or every batch run. Users notice the change the first day. |
| **3** | Clear improvement, but nobody's actively bleeding from the absence. Worth doing when convenient. |
| **2** | Nice-to-have polish. Makes the tool feel better but costs exceed felt pain. |
| **1** | Purely aesthetic or defensive. Only pays off in a future that may not arrive. |

Notes:
- A speculative architecture rewrite starts at 2 until real pain appears.
- A bug fix for a currently-broken workflow starts at 4 regardless of size.
- "This unblocks PRD-X" is only a multiplier if PRD-X itself is high value.

## Effort (xs/s/m/l/xl)

Realistic end-to-end work **given the current code state** — not what was
guessed at PRD-authoring time. "Current state" means the codebase as of this
worktree branch-point (origin/main at `b976797`).

| Bucket | Meaning |
|--------|---------|
| **xs** | <1 hour. One file, one obvious edit, trivial tests. |
| **s**  | A few hours to one day. Single module, focused tests, no new abstractions. |
| **m**  | 1–3 days. Multiple modules, a small new abstraction, moderate test surface. |
| **l**  | A week of focused work. New module/subsystem, cross-module integration, meaningful design work. |
| **xl** | Multiple weeks, multi-phase rollout, migration/compatibility work, or a genuine architectural shift. |

Factor into effort:
- **Discovery tax** if the PRD text is stale vs. current code (rare — PR #173
  caught most of this), or if acceptance criteria are underspecified.
- **Test surface** — if the AC list demands broad end-to-end coverage, bump up.
- **Coordination** with in-flight work (e.g., siblings landing into the same
  file) — bump up.

## Current state taxonomy

Each assessment tags a current-state bucket:

- **greenfield** — nothing built; PRD is the complete scope.
- **scaffolded** — some of the target modules/files exist but are empty or stubs.
- **partially landed** — real functionality exists but doesn't cover the AC list.
- **drift / already done** — the code already delivers the intent; the PRD is
  stale state, not an implementation gap. Recommendation is typically
  *close / mark superseded*.
- **blocked on upstream** — no work can start until a named dependency lands.

## Recommendation verbs

| Verb | Meaning |
|------|---------|
| **do-now** | Top of queue. Value/effort ratio is high and there's no reason to wait. |
| **do-next** | Should land soon, usually after a specific upstream. |
| **defer** | Keep on the backlog but don't prioritize. Re-score in a month. |
| **merge-into-X** | Fold into another PRD rather than shipping separately. |
| **split** | Scope is too broad; break into smaller executable pieces first. |
| **supersede** | Already landed / better handled elsewhere. Flip status and close. |
| **drop** | Value is below the threshold at which tracking overhead is worth it. |

## What "gaps remain to implement fully" means

For each PRD the assessment lists the *delta* between the current code state
and the PRD's acceptance criteria. Gaps are concrete enough that a planner
could convert them directly into task-level children or into a single-PR
implementation plan.
