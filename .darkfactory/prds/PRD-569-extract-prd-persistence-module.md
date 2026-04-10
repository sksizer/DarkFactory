---
id: PRD-569
title: "Extract PRD serialization and persistence into dedicated module"
kind: task
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/prd.py
  - src/darkfactory/persistence.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - refactor
  - architecture
  - frontmatter
---

# Extract PRD serialization and persistence into dedicated module

## Summary

`prd.py` (489 LOC) mixes three concerns: the `PRD` data model, YAML frontmatter parsing/serialization, and file I/O with surgical mutation. Extract the serialization and persistence logic into a dedicated module (`persistence.py` or `model.py`) so the data model is clean and the round-trip logic is consolidated in one place.

## Motivation

The current layout makes round-trip bugs (like PRD-568's date quoting) hard to reason about because parsing, serialization, surgical field edits, and full re-serialization are interleaved with the data model and helper functions like `parse_wikilink` and `_coerce_list`. A dedicated persistence module would:

1. Consolidate all YAML ↔ Python conversion in one place (load, dump, surgical edit, date normalization)
2. Keep `prd.py` focused on the `PRD` dataclass and its typed accessors
3. Make it easier to add format-preserving guarantees (quoting, key order, whitespace) without touching the model
4. Provide a clear seam if the storage format ever changes (e.g., TOML, SQLite)

## Scope

Move these functions out of `prd.py` into `persistence.py`:

| Function | LOC | Responsibility |
|----------|-----|---------------|
| `_split_frontmatter` | ~15 | Parse `---` delimited YAML block |
| `parse_prd` | ~30 | YAML → PRD dataclass |
| `load_all` | ~15 | Directory scan + parse |
| `dump_frontmatter` | ~10 | dict → YAML string |
| `write_frontmatter` | ~15 | Full re-serialization to disk |
| `update_frontmatter_field_at` | ~45 | Surgical line-level field edit |
| `set_status` / `set_status_at` | ~25 | Status + updated field mutation |
| `set_workflow` | ~20 | Workflow field mutation |
| `normalize_list_field_at` | ~30 | List field canonicalization |

Keep in `prd.py`:
- `PRD` dataclass
- `parse_id_sort_key`, `parse_wikilink`, `parse_wikilinks`
- `PRD_ID_RE`, `WIKILINK_RE`, `FRONTMATTER_RE` (used by both modules)
- `_coerce_list`, `_slug_from_filename`

## Technical approach

1. Create `src/darkfactory/persistence.py`
2. Move the functions listed above, keeping their signatures identical
3. Add re-exports from `prd.py` for backwards compatibility: `from .persistence import parse_prd, load_all, set_status, ...`
4. Update direct importers to use `persistence` (optional -- re-exports make this non-urgent)
5. Verify all tests pass without changes

The re-export approach means no caller needs to change immediately. Callers can be migrated incrementally.

## Acceptance criteria

- [ ] AC-1: `persistence.py` exists with all serialization/persistence functions
- [ ] AC-2: `prd.py` contains only the `PRD` dataclass and parsing helpers (regexes, wikilinks, coercion)
- [ ] AC-3: `from darkfactory.prd import parse_prd, load_all, set_status` still works via re-exports
- [ ] AC-4: All existing tests pass without modification
- [ ] AC-5: `mypy --strict` passes
- [ ] AC-6: No functional changes -- pure code movement

## References

- [[PRD-568-yaml-date-quoting-consistency]] -- would benefit from this split (date normalization lives in persistence)
- [[PRD-214-frontmatter-roundtrip-drift]] -- introduced `update_frontmatter_field_at`, the surgical edit path
