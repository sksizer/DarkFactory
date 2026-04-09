---
id: PRD-550
title: Flag downstream PRDs when an upstream change invalidates their assumptions
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-546-impact-declaration-drift-detection]]"
blocks: []
impacts:
  - src/darkfactory/impacts.py
  - src/darkfactory/prd.py
  - src/darkfactory/cli.py
  - prds/README.md
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - planning
  - reliability
---

# Flag downstream PRDs when an upstream change invalidates their assumptions

## Summary

When a PRD merges, other in-flight PRDs whose plans were written against the *old* state of the files it touched can silently go stale. Their acceptance criteria, code snippets, line counts, file paths, and decomposition reasoning may no longer match reality — but nothing in the system surfaces that.

This PRD adds a mechanism to **detect and flag downstream planning documents affected by an upstream change**, so a human (or the harness) can decide whether to re-plan, rebase, or discard.

## Motivation

Concrete example: `PRD-549-builtins-package-split.md` cites "582 lines, 9 public builtins, 7 private helpers" and enumerates each builtin by name in its decomposition DAG. If `PRD-548-lint-attribution-builtin` merges first and adds/renames/removes a builtin, PRD-549's child PRD list, line counts, AC-1 ("All 283 existing tests continue to pass"), and module layout diagram are all subtly wrong. Nothing alerts the author.

Generalizing:

- PRDs declare `impacts: [file1, file2, ...]` in frontmatter.
- When a PRD merges, we already know (or can compute, per PRD-546) the actual set of files it changed.
- Any *other* draft/ready/in-progress PRD that lists one of those files in its own `impacts:` is a candidate for re-review.
- Today this is invisible — authors rediscover it only when planning fails or a conflict explodes at execution time.

## Proposed approach

### Option A — new status/workflow state

Add a state such as `needs-refresh` (or `stale`) that a PRD can be moved into automatically when an upstream merge touches one of its impacted files. The PRD stays in this state until an author reviews it and either:

- re-promotes to `ready` (no changes needed, or changes applied), or
- edits the plan to reflect the new reality.

### Option B — new frontmatter field

Add an `upstream_changes:` list to frontmatter, populated automatically:

```yaml
upstream_changes:
  - prd: PRD-548
    merged: 2026-04-08
    overlapping_impacts:
      - src/darkfactory/builtins.py
    acknowledged: false
```

Tooling (and the author) can see at a glance which upstream merges have not yet been acknowledged. Clearing the list (or setting `acknowledged: true`) is an explicit human step.

**Recommendation:** Option B layered on top of a lightweight status transition. The field carries the *evidence*; the status is the *signal*. A PRD with unacknowledged upstream changes is automatically rendered/filtered as stale in the dashboard and in `just prd-list`.

### Detection mechanism

Two triggers:

- **Post-merge** (PR merged to `main`): original trigger described below.
- **Post-run** (graph execution): [[PRD-220-graph-execution]] emits a `{prd_id, changed_files}` event per completed run in its JSON stream. PRD-550 can consume this stream to flag downstream PRDs *as they're being produced by the graph executor*, not just on final merge. This is especially valuable inside an epic that's fanning out — stale-flag siblings before the whole epic lands.

1. On PRD merge (post-merge hook or scheduler tick), compute the set of files actually changed (reuse PRD-546's drift-detection machinery where possible — same file-set computation).
2. Scan all non-terminal PRDs (`draft`, `ready`, `in-progress`, `planning`) whose `impacts:` list intersects that set.
3. For each match, append an entry to `upstream_changes:` in the downstream PRD's frontmatter and (optionally) transition status.
4. Emit a summary to stdout / the PR body / the dashboard so humans see the fan-out.

### Scope of "impact"

- **File-level** overlap is the MVP. Cheap, already declared, good enough for most cases.
- **Symbol-level** (function/class) overlap is a possible follow-up — would require parsing the merged diff against declared symbols. Out of scope here.
- Declared impacts that are *documents* (e.g. `prds/README.md`) count too: a PRD that rewrites the PRD conventions should flag every in-flight PRD that cites the conventions doc.

## How this changes the 549 example

If PRD-548 merges and touches `src/darkfactory/builtins.py`, and PRD-549 lists that file in its `impacts:`, the tooling would:

1. Append an `upstream_changes:` entry to PRD-549 pointing at PRD-548.
2. Move PRD-549 from `ready` → `needs-refresh` (or equivalent).
3. Surface it in the dashboard as blocked on human acknowledgement.
4. The PRD-549 author re-reads 549 with PRD-548's diff in mind, updates the line counts / enumeration / DAG, and re-promotes to `ready`.

Critically, the child PRDs 549.3a–i, once they exist, will also have `impacts:` entries and will *also* be flagged when their siblings merge — this is a feature, not a bug, and it exercises the same DAG-coordination concerns raised in PRD-547.

## Open questions

- [ ] Auto-transition status, or just annotate frontmatter and let a dashboard filter do the work? Auto-transition is louder but risks thrashing during a busy epic.
- [ ] How does this interact with **epic children** that intentionally all touch the same file (per PRD-549's conflict-stress recommendation)? Siblings shouldn't flag each other on every merge — needs a suppression rule like "same parent epic, same wave".
- [ ] Relationship to PRD-546 (drift detection) and PRD-547 (cross-epic scheduler). This PRD is the *notification* half of what 546 already computes; confirm we can share one file-set diff pipeline instead of two.
- [ ] Does `acknowledged` live in frontmatter, in a sidecar file, or as a git trailer on the commit that re-promotes the PRD? Frontmatter is simplest but noisy in diffs.
- [ ] Retroactive scan: should a one-shot `just prd-scan-upstream` exist for PRDs that were already stale before this feature shipped?

## References

- [[PRD-220-graph-execution]] — surfaces per-run changed-file events that PRD-550 consumes to flag stale PRDs mid-epic.
- [[PRD-546-impact-declaration-drift-detection]] — computes the actual-vs-declared file set; reuse its pipeline.
- [[PRD-547-cross-epic-scheduler-coordination]] — related coordination problem across epics.
- [[PRD-549-builtins-package-split]] — concrete example of a PRD vulnerable to upstream churn.
