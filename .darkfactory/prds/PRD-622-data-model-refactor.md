---
id: PRD-622
title: Data Model Refactor
kind: epic
status: ready
priority: medium
effort: l
capability: complex
parent:
depends_on: []
blocks:
  - "[[PRD-623-model-module-extraction]]"
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

# Data Model Refactor

## Summary

Introduce a `data/` directory under `.darkfactory/` that houses `prds/`, `archive/`, and future extensible data types as peer folders. Extract a `model` module that owns dataclass definitions, domain logic, and internal persistence, and stamp every written PRD file with the app version.

## Motivation

The current layout puts PRDs directly under `.darkfactory/prds/` with no room for additional data types (ADRs, specs, etc.) without ad-hoc path additions. PRD parsing, dataclass definitions, and file I/O are tangled in a single `prd.py`. There is no way to know which version of DarkFactory last wrote a file, making future migrations guesswork. Archiving PRDs has no first-class support — completed work just accumulates alongside active items, and there is no way to move PRDs out of the active set while preserving cross-references.

## Requirements

### Functional

1. **Data directory structure** — All data lives under `.darkfactory/data/`. `prds/` and `archive/` are peer folders within it. Future data types are added as additional peer folders.
2. **Config: `data_dir`** — `.darkfactory/config.toml` gains a `data_dir` key (default: `.darkfactory/data/`). All code resolves PRD and archive paths relative to `data_dir`.
3. **Model module** — New `src/darkfactory/model/` package containing:
   - `_prd.py` — PRD dataclass and domain logic (moved from `prd.py`)
   - `_persistence.py` — Frontmatter read/write, file discovery across `data_dir` subfolders (internal to model, no public API yet)
   - `_migration.py` — Migration logic for `darkfactory migrate`
   - `__init__.py` — Public API surface (load, save, archive, migrate)
4. **App version stamping** — Every PRD write inserts/updates `app_version: X.Y.Z` in the YAML frontmatter. The version is sourced from `importlib.metadata.version("darkfactory")` (replacing the hardcoded `__version__` in `__init__.py`).
5. **Cross-folder PRD discovery** — `load_all()` discovers PRD files across all subfolders under `data_dir` (prds, archive, future types) so that frontmatter references (`parent`, `depends_on`, `blocks`) can resolve to PRDs regardless of which folder they live in. Wikilink parsing itself is unchanged — it extracts bare IDs from `[[PRD-NNN-slug]]` strings.
6. **Archive command** — `darkfactory archive PRD-NNN` moves the file from `data/prds/` to `data/archive/`, sets `status: archived`, and stamps `app_version`.
7. **Unarchive** — Deferred. We may add `darkfactory unarchive` later; for now, manual move + status change is acceptable.
8. **Migration command** — `darkfactory migrate [--directory DIR]` performs:
   - Creates `.darkfactory/data/` and `.darkfactory/data/archive/`
   - Moves contents of `.darkfactory/prds/` into `.darkfactory/data/prds/`
   - Stamps `app_version` into every PRD file's frontmatter
   - Updates `config.toml` with `data_dir` if not already set
   - Works on any project directory via `--directory`, matching existing CLI semantics
9. **Callsite migration** — All imports and references to the old `prd.py` module are updated to use `model`. No re-exports or shims from the old path.

### Non-Functional

1. **No backwards compatibility layer** — Old `prd.py` is removed. No re-exports.
2. **Obsidian compatibility** — Folder restructuring must not break Obsidian vault resolution (Obsidian searches recursively within the vault root).
3. **Test coverage** — Migration, archive, persistence, and wikilink resolution each have dedicated tests.
4. **mypy strict** — All new code passes mypy strict, consistent with project standards.

## Technical Approach

### Directory layout (after migration)

```
.darkfactory/
  config.toml          # gains data_dir key
  data/
    prds/              # active PRDs (moved from .darkfactory/prds/)
    archive/           # archived PRDs
```

### Module layout

```
src/darkfactory/
  model/
    __init__.py        # public API: load_all, load_one, save, archive, migrate
    _prd.py            # PRD dataclass, domain helpers (from old prd.py)
    _persistence.py    # read/write frontmatter, discover files across data_dir
    _migration.py      # darkfactory migrate implementation
  # prd.py             # DELETED — callsites updated
```

### App version sourcing

Replace `__version__ = "0.1.0"` in `__init__.py` with:
```python
from importlib.metadata import version
__version__ = version("darkfactory")
```

Persistence stamps `app_version: {__version__}` into frontmatter on every `save()` call.

### File discovery

`_persistence.py` provides a `discover(data_dir: Path) -> list[Path]` function that globs `PRD-*.md` across all immediate subdirectories of `data_dir`. This powers `load_all()` so that frontmatter references (`parent`, `depends_on`, `blocks`) resolve to PRDs regardless of folder. Most commands will filter to active-only after loading.

### Archive flow

1. Resolve PRD file path (must be in `data/prds/`)
2. Move file to `data/archive/`
3. Update frontmatter: `status: archived`, `app_version: X.Y.Z`, `updated: <today>`
4. Write file at new location

### Migration flow

1. Detect `.darkfactory/prds/` exists and `.darkfactory/data/prds/` does not
2. Create `.darkfactory/data/` and `.darkfactory/data/archive/`
3. Move `.darkfactory/prds/` to `.darkfactory/data/prds/`
4. For each `PRD-*.md` in `data/prds/`, stamp `app_version` in frontmatter
5. Update `config.toml` to include `data_dir = ".darkfactory/data"`
6. Print summary of migrated files

## Acceptance Criteria

- [ ] AC-1: `.darkfactory/data/prds/` is the default location for active PRDs
- [ ] AC-2: `.darkfactory/data/archive/` exists and `darkfactory archive PRD-NNN` moves a PRD there with `status: archived`
- [ ] AC-3: Every PRD write (save, archive, migrate) stamps `app_version` in frontmatter
- [ ] AC-4: `darkfactory migrate --directory DIR` migrates a legacy `.darkfactory/prds/` layout to the new `data/` structure
- [ ] AC-5: `model/` module is the sole owner of PRD dataclass, load/save, and archive logic — old `prd.py` is removed
- [ ] AC-6: `load_all()` discovers PRDs across both `prds/` and `archive/` so frontmatter references resolve correctly
- [ ] AC-7: `config.toml` supports `data_dir` key; all path resolution uses it
- [ ] AC-8: All new code passes mypy strict and has peer test files

## Open Questions

- DEFERRED: Unarchive command — what should the UX look like? Manual move is fine for now.
- DEFERRED: Schema versioning (distinct from app version) — will be addressed in a follow-up PRD.
- DEFERRED: Additional data types beyond PRDs (ADRs, specs) — this PRD builds the extensible structure; populating new types is future work.
- OPEN: Should `load_all()` return PRDs from archive by default, or require an explicit `include_archived=True` flag? Leaning toward flag to keep active-set queries clean.

## References

- Current `prd.py`: `src/darkfactory/prd.py`
- Current discovery: `src/darkfactory/discovery.py`
- Config resolution: `src/darkfactory/config.py`
- CLI `--directory` semantics: `src/darkfactory/discovery.py:36`

