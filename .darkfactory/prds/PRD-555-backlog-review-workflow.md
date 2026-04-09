---
id: PRD-555
title: backlog_review workflow — audit every ready PRD against current code state
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - workflows/backlog_review/workflow.py
  - workflows/backlog_review/prompts/role.md
  - workflows/backlog_review/prompts/task.md
  - workflows/backlog_review/prompts/verify.md
  - src/darkfactory/cli.py
  - tests/test_backlog_review_workflow.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - workflows
  - hygiene
  - planning
  - reliability
---

# `backlog_review` workflow — audit every ready PRD against current code state

## Summary

A new workflow that walks every `draft`/`ready`/`in-progress` PRD in the repo and audits it against the current state of the codebase. For each PRD it verifies still-relevant, updates stale `impacts:` lists, flags obsolete assumptions, and surfaces anything that needs human attention. The output is a structured review report plus (where safe) automatic edits to PRD frontmatter.

## Motivation

The PRD set drifts constantly:

- **`impacts:` rot.** A PRD written against `src/darkfactory/builtins.py` (when it was a single file) becomes wrong the moment PRD-549 splits that file into a package. No automatic detection today.
- **Obsolete PRDs.** Work gets done via a different route, the problem disappears, or the approach is superseded by a later PRD. Without review, these linger in `ready` forever.
- **Stale technical approaches.** A PRD cites specific line numbers, function signatures, or file layouts that have since changed. Running the PRD against today's code would produce a wrong-shaped diff.
- **Missing `depends_on` edges.** A PRD that didn't know about PRD-X when it was written might now be blocked on it.
- **Dead references.** Wikilinks to deleted/renumbered PRDs.
- **New code areas unclaimed.** A module was added to the codebase but no PRD's `impacts:` references it — might be deliberate (third-party) or might mean a PRD is missing.

Today the only mechanism for this is "read every PRD by hand periodically." That doesn't scale past ~30 PRDs; this repo already has 60+.

## Requirements

### Workflow shape

Sibling of `workflows/planning/` — same directory convention, same `workflow.py` + `prompts/` structure.

```
workflows/backlog_review/
├── __init__.py
├── workflow.py
└── prompts/
    ├── role.md
    ├── task.md       # one template, re-used per PRD
    └── verify.md
```

### Entry point

Not a per-PRD run — it operates on the **whole backlog**. Options for invocation:

- **(a)** A new CLI subcommand `prd review-backlog` that runs the workflow without needing a specific PRD id.
- **(b)** Attach the workflow to a "meta-PRD" that exists purely to be the review target (e.g. an evergreen `PRD-000-backlog-review`).
- **(c)** A workflow whose `applies_to` matches nothing automatically; it's only runnable via `prd run --workflow backlog_review <any-prd>`.

**Recommendation: (a)** — a real CLI command. The workflow is about orchestrating agent runs across many PRDs; fitting it into the PRD-per-run model is awkward.

### What the workflow does per PRD

For each PRD in scope (default: `status in {draft, ready, in-progress}`):

1. **Read the PRD** end-to-end.
2. **For each file in `impacts:`**, check:
   - Does it still exist? (If no → flag.)
   - Has it moved/been renamed? (Suggest new path.)
   - Has it been significantly rewritten since the PRD was last updated? (Count: lines added/removed in `git log --since={prd.updated}`.)
3. **Scan the body** for hardcoded line numbers, function signatures, and file paths. Grep the codebase for each. Flag anything that doesn't resolve.
4. **Check `depends_on` / `blocks`** wikilinks — every target must exist.
5. **Check for new potential dependencies.** If the PRD's body mentions a concept introduced by a later PRD (by substring match on title), suggest adding a `depends_on` edge.
6. **Check motivation still holds.** This is the hard one — a heuristic pass at best. Ask the agent to read the motivation section and flag if the cited problem appears to be already solved (via grep for feature keywords in recent commits).
7. **Decide an outcome** per PRD:
   - **`clean`** — no action needed.
   - **`stale-impacts`** — `impacts:` list needs updating; apply the fix automatically if the change is unambiguous.
   - **`stale-body`** — body cites things that don't match reality; flag for human.
   - **`likely-obsolete`** — motivation appears resolved; flag for human to cancel/close.
   - **`missing-deps`** — should `depends_on` other PRDs that didn't exist at write time; suggest the edges.
   - **`broken-refs`** — wikilinks point at nothing; flag for fix.

### Output

A single structured report written to `.backlog-review/YYYY-MM-DD.md` (git-ignored):

```markdown
# Backlog review — 2026-04-08

## Summary
- 62 PRDs reviewed
- 47 clean
- 8 stale-impacts (3 auto-fixed, 5 need review)
- 2 likely-obsolete
- 4 missing-deps
- 1 broken-refs

## PRD-123 — Some title [stale-impacts]
**Status:** ready
**Issue:** `src/darkfactory/builtins.py` was split into `src/darkfactory/builtins/` as of PRD-549.
**Recommendation:** Update impacts to `src/darkfactory/builtins/<specific-file>.py`.
**Auto-fix applied:** no (ambiguous — multiple new files).

## PRD-456 — Another title [likely-obsolete]
...
```

Plus, for PRDs where the fix is unambiguous (file renames, trivial path updates), apply the edit in place and commit with `chore(prd): backlog review auto-fixes`.

### Agent tool allowlist

- Read, Glob, Grep — broad read access to both PRDs and code.
- Write — scoped to `prds/**` for auto-fix edits.
- Bash — `uv run prd validate`, `git log`, `git show`, `git blame` (read-only git).
- No Write outside `prds/`, no push, no PR creation.

### Failure modes

- A single PRD review failure does not abort the whole run. Collect failures, report them, continue.
- The workflow writes the report even on partial failure.

### Scheduling

- Manual invocation initially. Later: a scheduled cron / CI job that runs weekly and opens a PR if auto-fixes are non-empty. Out of scope for this PRD.

## Acceptance criteria

- [ ] AC-1: `workflows/backlog_review/` exists with the canonical workflow + prompts structure.
- [ ] AC-2: `prd review-backlog` (or equivalent CLI entry point) runs the workflow over all draft/ready/in-progress PRDs.
- [ ] AC-3: For each PRD the workflow produces a per-PRD verdict from the documented set (`clean`, `stale-impacts`, `stale-body`, `likely-obsolete`, `missing-deps`, `broken-refs`).
- [ ] AC-4: `impacts:` fixes where a file was cleanly renamed are applied automatically and committed.
- [ ] AC-5: Ambiguous fixes and body-level issues are reported, not auto-applied.
- [ ] AC-6: A structured report is written to `.backlog-review/YYYY-MM-DD.md` with counts, verdicts, and per-PRD detail.
- [ ] AC-7: A single-PRD review failure does not abort the full run.
- [ ] AC-8: Tests cover the verdict classifier (pure function, no agent) with fixture PRDs.
- [ ] AC-9: Running on the current repo produces a usable first report — not perfect, but usable.

## Open questions

- [ ] Should the agent be allowed to propose new PRDs during review (e.g. "this area has no PRD coverage")? Probably not for v1 — scope creep. Out of scope.
- [ ] `depends_on` suggestion quality. Substring matching on titles is weak; symbol/concept matching would need a real embedding pass. v1 = substring, improve later.
- [ ] Batching: one agent invocation per PRD, or one big agent invocation reviewing the whole backlog? Per-PRD is more parallelizable (hello PRD-551) but 60+ agent runs is expensive. **Recommend: one invocation per "class" of PRD** — the agent handles N PRDs at once within a single session, capped at ~10-15 per session for context reasons.
- [ ] Interaction with [[PRD-550-upstream-impact-propagation]]. PRD-550 surfaces stale-flag events; backlog_review consumes the accumulated state. These should share machinery.
- [ ] Interaction with [[PRD-546-impact-declaration-drift-detection]]. Same concern — reuse the drift-detection file-set computation rather than rolling our own.

## References

- [[PRD-220-graph-execution]] — the graph executor is the downstream consumer of healthy backlog state.
- [[PRD-546-impact-declaration-drift-detection]] — shares file-level drift logic.
- [[PRD-550-upstream-impact-propagation]] — shares stale-PRD state.
- [[PRD-554-planning-workflow-prompt-hardening]] — the planning workflow is the upstream producer of the same PRDs we're reviewing; same quality concerns, opposite direction.
