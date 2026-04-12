# Batch 6 — Impact Assessment

## PRD-600.2.3 — Add --version flag to CLI
- **Impact:** none
- **Changes made:** none
- **Notes:** Already references the correct `cli/_parser.py` module from the PRD-556 CLI split. Approach is still valid.

## PRD-600.2.4 — Single-source the package version
- **Impact:** superseded
- **Changes made:**
  - `status: draft` -> `status: superseded`
  - Bumped `updated` to `'2026-04-11'`
  - Added `## Superseded by` section explaining PRD-622 already configured `[tool.hatch.version]` with `path = "src/darkfactory/__init__.py"` and `dynamic = ["version"]`
- **Notes:** Verified in `pyproject.toml` lines 3 and 29-30. Version is now single-sourced from `src/darkfactory/__init__.py:__version__`.

## PRD-600.2.5 — Add Python 3.13 to CI test matrix
- **Impact:** none
- **Changes made:** none
- **Notes:** Pure CI configuration, orthogonal to PRD-622.

## PRD-600.2.6 — Add tests for style.py
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal testing PRD; `style.py` module is unchanged by the refactor.

## PRD-600.2.7 — Delete dead cli.py stub file
- **Impact:** superseded
- **Changes made:**
  - `status: draft` -> `status: superseded`
  - Bumped `updated` to `'2026-04-11'`
  - Added `## Superseded by` section noting `src/darkfactory/cli.py` has already been removed
- **Notes:** Verified `src/darkfactory/cli.py` no longer exists. The monolithic stub file was deleted as part of the PRD-556 CLI split work; the `src/darkfactory/cli/` package (with per-subcommand submodules like `archive.py`, `validate.py`, `run.py`, etc.) replaced it.

## PRD-600.3 — Operational hardening and CLI quality improvements
- **Impact:** none
- **Changes made:** none
- **Notes:** Parent aggregator PRD. Its acceptance criteria are still valid. Child PRDs are addressed individually.

## PRD-600.3.1 — Extract _run_shell_once to shared runner utility
- **Impact:** none
- **Changes made:** none
- **Notes:** References `runner.py` and `system_runner.py`, which are unaffected by PRD-622. Approach is still valid.

## PRD-600.3.2 — Add --json support to validate command
- **Impact:** minor
- **Changes made:**
  - Updated `impacts:` from `src/darkfactory/cli/__init__.py` to `src/darkfactory/cli/validate.py`
  - Updated technical approach to point at `src/darkfactory/cli/validate.py` instead of `cli/__init__.py` lines 240-357 (that monolith no longer exists after the PRD-556 CLI split)
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Verified `cli/validate.py` exists.

## PRD-600.3.3 — Add --json support to tree command
- **Impact:** minor
- **Changes made:**
  - Updated `impacts:` from `src/darkfactory/cli/__init__.py` to `src/darkfactory/cli/tree.py`
  - Updated technical approach to point at `src/darkfactory/cli/tree.py` (the CLI split moved `cmd_tree` out of `cli/__init__.py`)
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Verified `cli/tree.py` exists.

## PRD-600.3.4 — Warn when --json is passed to unsupported command
- **Impact:** none
- **Changes made:** none
- **Notes:** Already references `cli/main.py`, which is the correct new location after the CLI split. Approach is still valid.
