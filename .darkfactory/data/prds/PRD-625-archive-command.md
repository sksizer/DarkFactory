---
id: PRD-625
title: Archive Command
kind: task
status: superseded
priority: medium
effort: s
capability: simple
parent:
depends_on:
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: '2026-04-11'
tags:
  - feature
---

# Archive Command

## Superseded by

PRD-622 delivered the full scope of this PRD as part of the data model refactor:

- The `prd archive PRD-NNN` CLI command exists (`python/darkfactory/cli/archive.py`) with guardrails requiring terminal status (`done`, `superseded`, `cancelled`) and transitive dependency checks (stricter than the original `in-progress` check proposed here).
- The `data/archive/` folder was introduced alongside `data/prds/` under `.darkfactory/data/`.
- `archive()` is implemented in `python/darkfactory/model/_persistence.py` and moves the file, stamps `app_version`, and writes via the deterministic serializer.
- `load_all(data_dir, *, include_archived=False)` discovers PRDs across both folders when requested.
- Callsites resolving frontmatter references use appropriate `include_archived` values.

PRD-622 also introduces `archived` as a new terminal status: it is added to `TERMINAL_STATUSES` in `python/darkfactory/model/_persistence.py:49`, and `archive()` flips the PRD's `status:` to `archived` on write. This matches PRD-625's original intent (the Summary section below already specifies `sets its status to archived`). The one approach difference is the guardrail: PRD-622 requires terminal status (`done`, `superseded`, `cancelled`) plus a transitive dependency check via BFS across the parent/children/depends_on/blocks axes, rather than simply blocking when an in-progress PRD is encountered.

## Summary

Add a `darkfactory archive PRD-NNN` CLI command that moves a PRD from `data/prds/` to `data/archive/`, sets its status to `archived`, and stamps `app_version`. Update `load_all()` to discover PRDs across both folders with an `include_archived` flag.

## Motivation

Completed PRDs accumulate alongside active work, cluttering status views and workflow routing. Archiving moves them out of the active set while preserving cross-references — active PRDs can still reference archived ones via frontmatter links because `load_all()` searches across all data subfolders.

## Requirements

### Functional

1. **Archive command** — `darkfactory archive PRD-NNN [--directory DIR]`:
   - Resolves PRD file in `data/prds/`
   - Moves file to `data/archive/`
   - Updates frontmatter: `status: archived`, `app_version: X.Y.Z`, `updated: <today>`
   - Prints confirmation
2. **Cross-folder discovery** — `load_all()` gains an `include_archived: bool = False` parameter. When `True`, discovers PRD files in both `data/prds/` and `data/archive/`. Default is active-only.
3. **Reference resolution** — Any code that resolves frontmatter references (`parent`, `depends_on`, `blocks`) uses `include_archived=True` so links to archived PRDs don't break.
4. **Guard rails** — Cannot archive a PRD that is `in-progress`. Error message if PRD not found.

### Non-Functional

1. mypy strict on all new/modified code
2. Peer tests for archive logic and cross-folder discovery
3. CLI help text for the new command

## Technical Approach

1. Add `archive()` function to `model/` — handles move + frontmatter update
2. Add `archive` subcommand to CLI parser
3. Update `_persistence.py` `discover()` to accept scope parameter (active-only vs all)
4. Update `load_all()` with `include_archived` flag
5. Audit callsites that resolve PRD references to ensure they use `include_archived=True`

## Acceptance Criteria

- [ ] AC-1: `darkfactory archive PRD-NNN` moves file to `data/archive/` with `status: archived`
- [ ] AC-2: `load_all(include_archived=True)` discovers PRDs in both `prds/` and `archive/`
- [ ] AC-3: Frontmatter references resolve to archived PRDs
- [ ] AC-4: Cannot archive an `in-progress` PRD
- [ ] AC-5: Tests cover archive, cross-folder discovery, and guard rails

## Open Questions

- DEFERRED: Unarchive command — manual move + status change is acceptable for now.

## References

- Parent epic: PRD-622

## Assessment (2026-04-11)

- **Value**: n/a — fully delivered.
- **Effort**: n/a
- **Current state**: drift / done. PRD-622 delivered the full
  scope of this PRD:
  - `python/darkfactory/cli/archive.py` exists and the `archive`
    subcommand is wired in the parser (state survey confirmed).
  - `archive()` is implemented in
    `python/darkfactory/model/_persistence.py`.
  - `load_all(data_dir, *, include_archived=False)` is the
    post-PRD-622 signature.
  - `archived` is a terminal status in `TERMINAL_STATUSES`.
  - Guardrails are stricter than AC-4 (terminal status + BFS
    transitive-dependency check, not just "not in-progress").
- **Gaps**: none. Status is currently `ready` but the work is
  done — the PRD frontmatter hasn't caught up.
- **Recommendation**: supersede — flip to `superseded` in the
  sweep. This one should have been handled in PR #173's
  assessment but was only marked superseded on that branch,
  not on main. Fixing the drift in this PR.
