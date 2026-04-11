---
id: PRD-624
title: Data Directory and Migration
kind: task
status: ready
priority: medium
effort: m
capability: moderate
parent: "[[PRD-622-data-model-refactor]]"
depends_on:
  - "[[PRD-623-model-module-extraction]]"
blocks:
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

# Data Directory and Migration

## Summary

Introduce the `.darkfactory/data/` directory structure with `prds/` and `archive/` as peer folders, add a `data_dir` config key, stamp `app_version` on every PRD write, and provide a `darkfactory migrate` command to move existing projects to the new layout.

## Motivation

PRDs currently live directly under `.darkfactory/prds/` with no room for additional data types or archiving. There is no way to know which version of DarkFactory last wrote a file, making future migrations guesswork. A migration command is needed because multiple projects need to move to the new structure.

## Requirements

### Functional

1. **Directory structure** — `.darkfactory/data/` is the new root, with `prds/` and `archive/` as immediate children
2. **Config key** — `config.toml` gains `data_dir` (default: `.darkfactory/data/`). All path resolution uses this.
3. **App version stamping** — Replace `__version__ = "0.1.0"` in `__init__.py` with `importlib.metadata.version("darkfactory")`. Every PRD write (via `save()`) stamps `app_version: X.Y.Z` in frontmatter.
4. **Migration command** — `darkfactory migrate [--directory DIR]`:
   - Creates `.darkfactory/data/` and `.darkfactory/data/archive/`
   - Moves contents of `.darkfactory/prds/` into `.darkfactory/data/prds/`
   - Stamps `app_version` into every PRD file's frontmatter
   - Updates `config.toml` with `data_dir` if not already set
   - Prints summary of migrated files
   - Uses standard `--directory` semantics from `discovery.py`
5. **Idempotent migration** — Running `migrate` on an already-migrated project is a no-op with a message

### Non-Functional

1. mypy strict on all new/modified code
2. Migration has dedicated tests (pre/post directory state assertions)
3. Existing tests updated for new default paths

## Technical Approach

1. Add `_migration.py` to `model/` package
2. Add `migrate` subcommand to CLI parser
3. Update `config.py` to support `data_dir` key with default
4. Update `_persistence.py` to resolve paths relative to `data_dir`
5. Modify `save()` to stamp `app_version` on every write
6. Switch `__init__.py` to `importlib.metadata.version()`
7. Update all code that references the old `prd_dir` default path

## Acceptance Criteria

- [ ] AC-1: `.darkfactory/data/prds/` is the default location for active PRDs
- [ ] AC-2: `config.toml` supports `data_dir` key; all path resolution uses it
- [ ] AC-3: Every PRD write stamps `app_version` in frontmatter
- [ ] AC-4: `darkfactory migrate --directory DIR` migrates a legacy layout to the new structure
- [ ] AC-5: Migration is idempotent — second run is a safe no-op
- [ ] AC-6: `__version__` sourced from `importlib.metadata`

## Open Questions

None.

## References

- Config resolution: `src/darkfactory/config.py`
- CLI `--directory` semantics: `src/darkfactory/discovery.py:36`
- Parent epic: PRD-622
