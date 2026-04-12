---
id: PRD-622
title: Data Model Refactor
kind: task
status: done
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
updated: '2026-04-11'
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
   - `_prd.py` — PRD dataclass and domain logic (wikilink parsing, sort helpers, containment, regex constants)
   - `_persistence.py` — Frontmatter read/write, file discovery, auto-migration
   - `__init__.py` — Public API re-exporting the above
   - Delete `src/darkfactory/prd.py`. No re-exports or backwards-compat shims.
   - Update all callsites to import from `darkfactory.model`.

   **Public API signatures** (re-exported from `__init__.py`):
   - `load_all(data_dir: Path, *, include_archived: bool = False) -> dict[str, PRD]` — discover and load PRDs from `data_dir/prds/`; when `include_archived=True`, also scans `data_dir/archive/`
   - `load_one(data_dir: Path, prd_id: str, *, include_archived: bool = True) -> PRD` — find and load a single PRD by ID; searches `prds/` first, then `archive/`; raises `KeyError` if not found; default `include_archived=True` because the primary use case is reference resolution
   - `save(prd: PRD) -> None` — write PRD to `prd.path` using deterministic serialization (canonical field order, explicit quoting rules); stamps `app_version` and `updated`
   - `set_status(prd: PRD, new_status: str) -> None` — mutates `prd.status`, then calls `save`
   - `set_status_at(path: Path, new_status: str) -> None` — path-targeted variant for worktree copies (does not stamp `app_version` — worktree writes are ephemeral); only function that retains surgical line-editing
   - `archive(prd: PRD, data_dir: Path) -> PRD` — guardrail check, move file, update frontmatter, return updated PRD with new `path`

   Existing helpers (`parse_prd`, `dump_frontmatter`, `normalize_list_field_at`, `set_workflow`, `compute_branch_name`, `parse_id_sort_key`, `parse_wikilink`, `parse_wikilinks`) remain importable from `darkfactory.model` but are internal — not part of the documented public API contract.

2. **Data directory structure** — `.darkfactory/data/` contains `prds/` and `archive/` as peer folders. Paths resolved during config assembly and stored in the `Config` object (system paths section).
   - Update `init.py`: `_REQUIRED_DIRS` changes from `.darkfactory/prds/` to `.darkfactory/data/prds/` and adds `.darkfactory/data/archive/`. New projects scaffold the new layout directly.
   - Update `main.py`: replace `args.prd_dir = darkfactory_dir / "prds"` with `args.data_dir = darkfactory_dir / "data"`. All callsites that referenced `args.prd_dir` migrate to `args.data_dir`; those needing the prds subdirectory specifically use `args.data_dir / "prds"`.

3. **Auto-migration** — `ensure_data_layout()` runs in CLI `main()` before command dispatch. Detects legacy layout (`.darkfactory/prds/` exists, `.darkfactory/data/prds/` does not) and migrates interactively:
   - Print what will happen (file count, source → destination)
   - If TTY: prompt user for confirmation before proceeding
   - If non-TTY: print migration notice to stderr and exit non-zero with instructions to run interactively
   - Create `.darkfactory/data/` and `.darkfactory/data/archive/`
   - Move all contents of `.darkfactory/prds/` (including `Dashboard.base`) into `.darkfactory/data/prds/`
   - Stamp `app_version` into every migrated PRD's frontmatter
   - Print summary of migrated files
   - No rollback logic — use `git revert` if needed.

4. **App version stamping** — All writes through the model's public API (`save`, `set_status`, `set_workflow`, `archive`) stamp `app_version: X.Y.Z` in YAML frontmatter. Since `set_status`, `set_workflow`, and `archive` all delegate to `save`, stamping is enforced in one place. Exception: `set_status_at` (worktree variant) does not stamp — worktree writes are ephemeral. Version sourced from `__version__` in `__init__.py` (single source of truth). Configure hatchling to read version from code:
   ```toml
   [tool.hatch.version]
   path = "src/darkfactory/__init__.py"
   ```

5. **Archive command** — `darkfactory archive PRD-NNN`:
   - Moves PRD file from `data/prds/` to `data/archive/`
   - Updates frontmatter: `status: archived`, `app_version: X.Y.Z`, `updated: <today>`
   - Updates `prd.path` on the returned PRD object to reflect the new location
   - **Guardrails**: Only PRDs in a terminal state (`done`, `superseded`, or `cancelled`) can be archived. Additionally, the PRD's full transitive dependency chain — in both directions on both the parenting axis (ancestors/descendants) and the dependency axis (depends_on/blocks) — must also be in a terminal state. All violations produce an error listing the blocking PRDs.
   - **Guardrail algorithm**: Starting from the target PRD, BFS/DFS along four edge types: (a) parent axis upward — follow `parent` transitively to all ancestors, (b) parent axis downward — follow reverse-parent lookup transitively to all descendants, (c) dependency axis forward — follow `depends_on` transitively, (d) dependency axis backward — follow `blocks` transitively. Collect the union of all reachable PRDs. Every PRD in the set must be in a terminal state (`done`, `superseded`, `cancelled`, or `archived`). Non-terminal PRDs are reported as blockers with their IDs and current statuses. Uses `load_all(data_dir, include_archived=True)` to resolve references across both folders.

6. **Cross-folder discovery** — `load_all(data_dir: Path, *, include_archived: bool = False)` takes the `.darkfactory/data/` directory (not the `prds/` subdirectory). Internally derives `data_dir / "prds"` and `data_dir / "archive"`:
   - Default (`include_archived=False`): discovers PRDs in `data_dir/prds/` only. This is the correct default for nearly all CLI commands (status, next, validate, tree, run, etc.) — they operate on the active DAG only. Archive guardrails ensure that active PRDs cannot reference archived ones, so archived PRDs are effectively orphaned from the active graph.
   - `include_archived=True`: discovers across both `data_dir/prds/` and `data_dir/archive/`. Used by `archive()` itself (to run the transitive guardrail check against every existing PRD) and available to any caller that specifically needs to resolve an ID against both folders.
   - `load_one(data_dir, prd_id)` defaults to `include_archived=True` because single-PRD lookups are typically reference resolution (following a link from one PRD to another, where the target may have been archived).
   - Archived PRDs may drift from current data model over time; links are maintained but full model conformance is not guaranteed for old archived files. Document this as a known constraint.

7. **Callsite migration** — All imports and references to `prd.py` updated to `model`. No shims. This includes ~12 source files in `src/darkfactory/` and ~20 test files in `tests/` and peer test files.

8. **Remove `--prd-dir` CLI flag** — Delete the `--prd-dir` argument from `_parser.py`. It is unused externally and creates an unnecessary maintenance surface. The `--directory` / `DARKFACTORY_DIR` discovery mechanism is sufficient. Internal `args.prd_dir` references become `args.data_dir`.

9. **Test fixture migration** — Root `conftest.py` and test helpers: rename `tmp_prd_dir` fixture to `tmp_data_dir`, which creates the `prds/` and `archive/` subdirectory structure. Existing tests that write PRD files to `tmp_prd_dir` write to `tmp_data_dir / "prds"` instead. Approximately 20 test files need this mechanical update.

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

### Deterministic frontmatter serialization

Replace `yaml.safe_dump` in the write path with a custom serializer that guarantees stable output:

- **Canonical field order** — fixed sequence matching the PRD template: `id`, `title`, `kind`, `status`, `priority`, `effort`, `capability`, `parent`, `depends_on`, `blocks`, `impacts`, `workflow`, `assignee`, `reviewers`, `target_version`, `created`, `updated`, `app_version`, `tags`. Unknown fields (if any) appended alphabetically at the end.
- **Explicit quoting rules** — dates single-quoted (`'2026-04-11'`), wikilinks double-quoted (`"[[PRD-622-data-model-refactor]]"`), bare strings unquoted where YAML-safe, `null` for `None`.
- **List formatting** — block-style (`- item` on separate lines) for non-empty lists, `[]` for empty lists. Items sorted per `CANONICAL_SORTS`.
- **One write path** — `save()` is the only function that writes frontmatter (except `set_status_at` for worktrees). All other public write APIs (`set_status`, `set_workflow`, `archive`) mutate the PRD object in memory and delegate to `save()`. This eliminates the need for `write_frontmatter`, `update_frontmatter_field_at`, and the dual surgical/full-reserialize code paths.

Same logical content always produces the same bytes. Git diffs show only fields that actually changed.

### Config expansion

Expand the existing `Config` dataclass by adding a nested `PathsConfig` section alongside the existing `ModelConfig` and `StyleConfig`:
- **User preferences** — `config.model`, `config.style` (existing)
- **System paths** — `config.paths` with fields `project_dir`, `data_dir`, `prds_dir`, `archive_dir` (new, resolved from `.darkfactory/` location)

Keeping paths in their own nested dataclass mirrors how `model` and `style` are organized and avoids widening the flat `Config` surface. `resolve_config()` resolves all sections. `_persistence.py` receives paths as explicit function arguments (derived from `config.paths`) rather than importing constants directly.

### Auto-migration flow

`ensure_data_layout()` in CLI `main()`, runs before command dispatch:
1. Detect `.darkfactory/prds/` exists and `.darkfactory/data/prds/` does not
2. If non-TTY: print notice to stderr, exit non-zero with instructions
3. Print migration plan (file count, paths), prompt for confirmation
4. Create `.darkfactory/data/` and `.darkfactory/data/archive/`
5. Move `.darkfactory/prds/` → `.darkfactory/data/prds/` (all contents including `Dashboard.base`; delete old directory after move)
6. Stamp `app_version` in each PRD's frontmatter
7. Print migration summary to stderr

### Archive flow

1. Load PRD via `load_one(data_dir, prd_id)`
2. Check status is `done`, `superseded`, or `cancelled` — error otherwise
3. Run transitive guardrail check (BFS across parent/child/depends_on/blocks axes); error with blocker list if any non-terminal PRDs found
4. Compute destination path: `data_dir / "archive" / prd.path.name`
5. Move file from `data/prds/` to `data/archive/`
6. Update `prd.path` to the new location
7. Update frontmatter at new path: `status: archived`, `app_version`, `updated`
8. Return updated PRD

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/model/` package exists with `_prd.py`, `_persistence.py`, `__init__.py`
- [ ] AC-2: `src/darkfactory/prd.py` is deleted — no re-exports or shims
- [ ] AC-3: All callsites import from `darkfactory.model`
- [ ] AC-4: `.darkfactory/data/prds/` is the default location for active PRDs
- [ ] AC-5: `.darkfactory/data/archive/` exists and `darkfactory archive PRD-NNN` moves eligible PRDs there
- [ ] AC-6: Archive guardrails: only terminal-state PRDs (`done`, `superseded`, `cancelled`) can be archived, and only when their full transitive dependency chain (ancestors, descendants, depends_on, blocks — BFS across all four axes) is also terminal; `archive()` returns updated PRD with new `path`
- [ ] AC-7: `save()` uses deterministic serialization (canonical field order, explicit quoting); `set_status`, `set_workflow`, `archive` delegate to `save()`; all stamp `app_version`; `set_status_at` (worktree variant) does not
- [ ] AC-8: Auto-migration detects legacy layout, prompts interactively (or errors on non-TTY), migrates all contents including `Dashboard.base`; old `.darkfactory/prds/` directory is removed after move
- [ ] AC-9: `load_all(data_dir, *, include_archived=False)` discovers PRDs in `data_dir/prds/` by default; `include_archived=True` also scans `data_dir/archive/`; `load_one(data_dir, prd_id)` finds a single PRD by ID and defaults to `include_archived=True` for reference-resolution use cases
- [ ] AC-10: `pyproject.toml` uses `[tool.hatch.version]` to read version from `__init__.py`
- [ ] AC-11: `Config` dataclass gains a nested `PathsConfig` section (`config.paths.project_dir`, `config.paths.data_dir`, `config.paths.prds_dir`, `config.paths.archive_dir`); `_persistence.py` receives paths as explicit arguments derived from `config.paths`
- [ ] AC-12: `--prd-dir` CLI flag removed from `_parser.py`; `args.prd_dir` replaced with `args.data_dir` across all CLI commands
- [ ] AC-13: `init.py` scaffolds `.darkfactory/data/prds/` and `.darkfactory/data/archive/` for new projects
- [ ] AC-14: Test fixtures updated: `tmp_prd_dir` → `tmp_data_dir` with `prds/` and `archive/` subdirectories; all ~20 test files updated
- [ ] AC-15: All new code passes mypy strict, has peer test files, lint passes

## Open Questions

- RESOLVED: `data_dir` config key — paths resolved in `Config` (system paths section), not a user-facing config key.
- RESOLVED: Migration rollback — not needed; use `git revert`.
- RESOLVED: Unarchive command — deferred; manual move + status change is fine for alpha.
- RESOLVED: Archive guardrails — only `done`, `superseded`, `cancelled` can be archived; full transitive chain must also be terminal.
- RESOLVED: Migration interactivity — prompt on TTY, fail with instructions on non-TTY.
- RESOLVED: Config architecture — expand existing `Config` into single state tree (user prefs + system paths) rather than separate context object.
- RESOLVED: `Dashboard.base` — migrates with all other files in `.darkfactory/prds/`.
- RESOLVED: `--prd-dir` CLI flag — removed; unused externally, `--directory` / `DARKFACTORY_DIR` is sufficient.
- RESOLVED: `load_all` signature — takes `data_dir: Path` (`.darkfactory/data/`), not `prd_dir`. Derives subdirectories internally.
- RESOLVED: `PRD.path` after archive — updated to reflect new location before return.
- RESOLVED: `app_version` stamping scope — public write APIs stamp; surgical internals and worktree variant do not.
- RESOLVED: Archive guardrail traversal — full transitive BFS across all four axes (ancestors, descendants, depends_on, blocks).
- RESOLVED: Frontmatter serialization — deterministic custom serializer with canonical field order replaces `yaml.safe_dump`; eliminates surgical write workarounds and noisy git diffs.
- DEFERRED: Schema versioning (distinct from app version) — future PRD when model actually evolves.
- DEFERRED: Additional data types beyond PRDs (ADRs, specs) — this builds the extensible structure; new types are future work.

## References

- Current `prd.py`: `src/darkfactory/prd.py`
- Config resolution: `src/darkfactory/config.py`
- CLI entry: `src/darkfactory/cli/main.py`
- Prior decomposition (deleted): PRD-623, PRD-624, PRD-625
