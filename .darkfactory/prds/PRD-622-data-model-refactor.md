---
id: PRD-622
title: Data Model Refactor
kind: task
status: ready
priority: medium
effort: xl
capability: complex
parent:
depends_on: []
blocks: []
impacts: []
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: 2026-04-11
tags: []
---

# Data Model Refactor

## Summary

Extract a `model/` package from the monolithic `prd.py`, introduce `.darkfactory/data/` as the home for `prds/` and `archive/`, add a `darkfactory archive` command with status guardrails, stamp `app_version` on every PRD write, and auto-migrate legacy layouts on first run.

## Motivation

`prd.py` mixes dataclass definitions, YAML frontmatter I/O, file discovery, and domain helpers (wikilink parsing, natural sort, containment). This coupling makes it hard to add new data types or a distinct persistence layer.

Completed PRDs accumulate alongside active work with no way to move them out of the active set. An archive folder preserves cross-references while decluttering status views and workflow routing.

There is no way to know which version of DarkFactory last wrote a file, making future schema migrations guesswork.

## Requirements

### Functional

1. **Model module extraction** — Create `src/darkfactory/model/` package:
   - `_prd.py` — PRD dataclass and domain logic (wikilink parsing, sort helpers, containment)
   - `_persistence.py` — Frontmatter read/write, `load_all()`, `load_one()`, `save()`, file discovery
   - `__init__.py` — Public API re-exporting the above
   - Delete `src/darkfactory/prd.py`. No re-exports or backwards-compat shims.
   - Update all callsites to import from `darkfactory.model`.

2. **Data directory structure** — `.darkfactory/data/` contains `prds/` and `archive/` as peer folders. Path is hardcoded relative to `.darkfactory/` — no configurable `data_dir` key.

3. **Auto-migration** — On first run of any command, detect legacy layout (`.darkfactory/prds/` exists, `.darkfactory/data/prds/` does not) and automatically migrate:
   - Create `.darkfactory/data/` and `.darkfactory/data/archive/`
   - Move contents of `.darkfactory/prds/` into `.darkfactory/data/prds/`
   - Stamp `app_version` into every migrated PRD's frontmatter
   - Print summary of migrated files
   - No rollback logic — use `git revert` if needed.

4. **App version stamping** — Every PRD write (save, archive) stamps `app_version: X.Y.Z` in YAML frontmatter. Version sourced from `__version__` in `__init__.py` (single source of truth). This field is for internal troubleshooting only — no runtime consumers currently. Configure hatchling to read version from code:
   ```toml
   [tool.hatch.version]
   path = "src/darkfactory/__init__.py"
   ```

5. **Archive command** — `darkfactory archive PRD-NNN`:
   - Moves PRD file from `data/prds/` to `data/archive/`
   - Updates frontmatter: `status: archived`, `app_version: X.Y.Z`, `updated: <today>`
   - **Guardrails**: Only PRDs in a terminal state (`done`, `superseded`, or `cancelled`) can be archived. Additionally, the PRD's entire dependency chain — in both directions on both the parenting axis and the dependency axis — must also be in a terminal state. All violations produce an error listing the blocking PRDs.

6. **Cross-folder discovery** — `load_all()` gains an `include_archived: bool = False` parameter:
   - Default (False): discovers PRDs in `data/prds/` only
   - True: discovers across both `data/prds/` and `data/archive/`
   - Reference resolution (`parent`, `depends_on`, `blocks`) uses `include_archived=True` so links to archived PRDs don't break
   - Archived PRDs may drift from current data model over time; links are maintained but full model conformance is not guaranteed for old archived files. Document this as a known constraint.

7. **Callsite migration** — All imports and references to `prd.py` updated to `model`. No shims.

### Non-Functional

1. No backwards compatibility layer — old `prd.py` is deleted outright
2. Obsidian compatibility — Obsidian searches recursively within vault root; unique filenames (enforced by PRD ID) are sufficient
3. mypy strict on all new and modified files
4. Peer test files for `_prd.py` and `_persistence.py`; dedicated tests for archive logic, auto-migration, and cross-folder discovery

## Technical Approach

### Directory layout (after migration)

```
.darkfactory/
  config.toml
  data/
    prds/              # active PRDs (moved from .darkfactory/prds/)
    archive/           # archived PRDs (done, superseded, cancelled)
```

### Module layout

```
src/darkfactory/
  model/
    __init__.py        # public API: load_all, load_one, save, archive
    _prd.py            # PRD dataclass, domain helpers (from old prd.py)
    _persistence.py    # read/write frontmatter, discover files, auto-migrate
  # prd.py             # DELETED
```

### Version sourcing

Keep `__version__ = "0.1.0"` in `src/darkfactory/__init__.py` as the single source of truth. Add `[tool.hatch.version]` to `pyproject.toml` so hatchling reads it from code at build time — eliminates the duplication between `pyproject.toml` and `__init__.py`.

### Auto-migration flow

Triggered during app configuration (which nearly every command runs through):
1. Detect `.darkfactory/prds/` exists and `.darkfactory/data/prds/` does not
2. Create `.darkfactory/data/` and `.darkfactory/data/archive/`
3. Move `.darkfactory/prds/` → `.darkfactory/data/prds/` (delete the old directory after move)
4. Stamp `app_version` in each PRD's frontmatter
5. Print migration summary to stderr

### Archive flow

1. Load PRD, check status is `done`, `superseded`, or `cancelled` — error otherwise
2. Move file from `data/prds/` to `data/archive/`
3. Update frontmatter: `status: archived`, `app_version`, `updated`
4. Write file at new location

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/model/` package exists with `_prd.py`, `_persistence.py`, `__init__.py`
- [ ] AC-2: `src/darkfactory/prd.py` is deleted — no re-exports or shims
- [ ] AC-3: All callsites import from `darkfactory.model`
- [ ] AC-4: `.darkfactory/data/prds/` is the default location for active PRDs
- [ ] AC-5: `.darkfactory/data/archive/` exists and `darkfactory archive PRD-NNN` moves eligible PRDs there
- [ ] AC-6: Archive guardrails: only terminal-state PRDs (`done`, `superseded`, `cancelled`) can be archived, and only when their full dependency chain (parents, children, depends_on, blocks — both directions) is also terminal
- [ ] AC-7: Every PRD write stamps `app_version` in frontmatter
- [ ] AC-8: Auto-migration detects legacy layout and migrates during app configuration; old `.darkfactory/prds/` directory is removed after move
- [ ] AC-9: `load_all(include_archived=True)` discovers PRDs across both folders; reference resolution uses this
- [ ] AC-10: `pyproject.toml` uses `[tool.hatch.version]` to read version from `__init__.py`
- [ ] AC-11: All new code passes mypy strict, has peer test files, lint passes

## Open Questions

- RESOLVED: `data_dir` config key — omitted; path hardcoded relative to `.darkfactory/`.
- RESOLVED: Migration rollback — not needed; use `git revert`.
- RESOLVED: Unarchive command — deferred; manual move + status change is fine for alpha.
- RESOLVED: Archive guardrails — only `done`, `superseded`, `cancelled` can be archived.
- DEFERRED: Schema versioning (distinct from app version) — future PRD when model actually evolves.
- DEFERRED: Additional data types beyond PRDs (ADRs, specs) — this builds the extensible structure; new types are future work.

## References

- Current `prd.py`: `src/darkfactory/prd.py`
- Config resolution: `src/darkfactory/config.py`
- CLI entry: `src/darkfactory/cli/main.py`
- Prior decomposition (deleted): PRD-623, PRD-624, PRD-625
