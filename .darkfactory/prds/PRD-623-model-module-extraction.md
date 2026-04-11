---
id: PRD-623
title: Model Module Extraction
kind: task
status: ready
priority: medium
effort: m
capability: moderate
parent: "[[PRD-622-data-model-refactor]]"
depends_on: []
blocks:
  - "[[PRD-624-data-directory-and-migration]]"
  - "[[PRD-625-archive-command]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: 2026-04-11
tags: []
---

# Model Module Extraction

## Summary

Extract the PRD dataclass, domain logic, and file I/O from the monolithic `prd.py` into a new `src/darkfactory/model/` package. Delete the old `prd.py` and update all callsites. No behavior change — pure structural refactor.

## Motivation

`prd.py` currently mixes the PRD dataclass definition, YAML frontmatter parsing/writing, file discovery, and domain helpers (wikilink parsing, natural sort, containment). This coupling makes it difficult to add new data types or a distinct persistence layer. Extracting a `model/` package creates clean boundaries for the data directory and archive work that follows.

## Requirements

### Functional

1. Create `src/darkfactory/model/` package with:
   - `_prd.py` — PRD dataclass and domain logic (wikilink parsing, sort helpers, containment)
   - `_persistence.py` — Frontmatter read/write, `load_all()`, `load_one()`, `save()`, file discovery
   - `__init__.py` — Public API re-exporting the above
2. Delete `src/darkfactory/prd.py`
3. Update every import of `darkfactory.prd` across the codebase to use `darkfactory.model`
4. Preserve all existing behavior — this is a move, not a rewrite

### Non-Functional

1. mypy strict passes on all new and modified files
2. All existing tests pass without modification (beyond import path changes)
3. Peer test files created for `_prd.py` and `_persistence.py`

## Technical Approach

1. Create the `model/` package directory
2. Move PRD dataclass + domain helpers into `_prd.py`
3. Move load/save/discovery functions into `_persistence.py`
4. Set up `__init__.py` with the public API surface
5. Find all callsites via grep for `from darkfactory.prd import` and `from darkfactory import prd`
6. Update each callsite
7. Delete `prd.py` and `prd_test.py`, replace with new peer tests
8. Run full test suite + typecheck + lint

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/model/` package exists with `_prd.py`, `_persistence.py`, `__init__.py`
- [ ] AC-2: `src/darkfactory/prd.py` is deleted — no re-exports or shims
- [ ] AC-3: All callsites import from `darkfactory.model`
- [ ] AC-4: Full test suite passes, mypy strict passes, lint passes
- [ ] AC-5: No behavior change — all existing functionality preserved

## Open Questions

None.

## References

- Current `prd.py`: `src/darkfactory/prd.py`
- Parent epic: PRD-622
