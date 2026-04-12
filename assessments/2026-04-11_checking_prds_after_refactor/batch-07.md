# Batch 7 — Impact Assessment

## PRD-600.3.5 — Add --yes flag to cleanup --all
- **Impact:** none
- **Changes made:** none
- **Notes:** Already references `cli/_parser.py` and `cli/cleanup.py` (new per-subcommand modules). Technical approach still valid.

## PRD-600.3.6 — Add help text examples to top 5 commands
- **Impact:** none
- **Changes made:** none
- **Notes:** Already references `cli/_parser.py`. No stale references.

## PRD-600.3.7 — Add `prd show` command
- **Impact:** minor
- **Changes made:**
  - Replaced `src/darkfactory/cli/__init__.py` in `impacts` with `src/darkfactory/cli/show.py` + `cli/show_test.py` (matches new per-subcommand pattern).
  - Rewrote technical approach step 2 to instruct creating `cli/show.py` following the per-subcommand module pattern with a peer test file, and to use `darkfactory.model.load_one(args.data_dir, args.prd_id)`.
  - Bumped `updated` to `'2026-04-11'`.

## PRD-600.3.8 — Make project workflow loading failures loud
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `loader.py` / `registry.py`, orthogonal to PRD-622 and CLI split. Technical approach still valid.

## PRD-600.3.9 — Add pagination/warning to reconcile PR fetching
- **Impact:** minor
- **Changes made:**
  - Changed `impacts` from `cli/__init__.py` to `cli/reconcile.py`.
  - Updated the Summary and "Code location" sections to reference `cli/reconcile.py` (instead of `cli/__init__.py:1342-1360`, which no longer exists).
  - Bumped `updated`.

## PRD-600.4 — Frontend optionality seams
- **Impact:** minor
- **Changes made:**
  - Updated motivation to reference the `model/` package instead of `prd.py` as part of the already-separated domain layer.
  - Bumped `updated`.
- **Notes:** Scope (extract arg resolution, reconcile domain logic, --json coverage, HarnessError hierarchy) still fully valid after PRD-622.

## PRD-600.4.1 — Extract cmd_run argument resolution
- **Impact:** minor
- **Changes made:**
  - Changed `prepare_run()` signature parameter from `prd_dir: Path` to `data_dir: Path` (PRD-622 renamed the concept).
  - Added a note that `data_dir` is `.darkfactory/data/` and `load_one(data_dir, prd_id)` derives the `prds/` subdir internally.
  - Bumped `updated`.
- **Notes:** Still valid work — `cli/run.py` exists but `prepare_run()` has not been extracted.

## PRD-600.4.2 — Extract reconcile domain logic
- **Impact:** minor
- **Changes made:**
  - Changed the `apply_reconciliation()` signature parameter from `prd_dir` to `data_dir`.
  - Bumped `updated`.
- **Notes:** Still valid — `cli/reconcile.py` currently contains the full reconcile logic (verified: `_get_merged_prd_prs`, `_find_prd_file_for_branch`, etc. are all still in the CLI handler module). Domain module `src/darkfactory/reconcile.py` does not yet exist.

## PRD-600.4.3 — Add --json to remaining read commands
- **Impact:** minor
- **Changes made:**
  - Replaced `impacts: src/darkfactory/cli/__init__.py` with the five specific per-subcommand modules: `cli/children.py`, `cli/orphans.py`, `cli/undecomposed.py`, `cli/cleanup.py`, `cli/reconcile.py`.
  - Bumped `updated`.

## PRD-600.4.4 — Introduce HarnessError exception hierarchy
- **Impact:** minor
- **Changes made:**
  - Replaced `src/darkfactory/cli/__init__.py` in `impacts` with a wildcard `src/darkfactory/cli/*.py` entry (the SystemExit sites are now spread across all per-subcommand modules after the CLI split).
  - Kept `cli/main.py` and `errors.py`.
  - Bumped `updated`.
- **Notes:** Technical approach and effort estimate still valid.
