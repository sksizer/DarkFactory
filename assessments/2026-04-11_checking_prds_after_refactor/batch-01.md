# Batch 1 — Impact Assessment

## PRD-225.7 — Rework loop detection
- **Impact:** none
- **Changes made:** none
- **Notes:** References only `runner.py` and the rework workflow module. No stale paths, no prd.py imports, no tmp_prd_dir. Unaffected by PRD-622.

## PRD-226 — Derive PRD status from event log + git history
- **Impact:** minor
- **Changes made:**
  - Updated two illustrative layout references (`prds/PRD-X.md` -> `.darkfactory/data/prds/PRD-X.md`) in the "Source of truth" table
  - Updated proposed event log path (`.darkfactory/events/` -> `.darkfactory/data/events/`) to match the new data layout
  - Bumped `updated` to 2026-04-11
- **Notes:** This is a future/draft architectural epic. Approach is still valid — it proposes a conceptual direction (status as derived view) orthogonal to PRD-622's serialization refactor.

## PRD-229 — Hardened planning workflow
- **Impact:** minor
- **Changes made:**
  - `impacts:` rewritten: `workflows/planning/workflow.py` -> `src/darkfactory/workflows/planning/workflow.py`; `src/darkfactory/builtins.py` -> `src/darkfactory/builtins/**`; `tests/test_planning_workflow.py` -> `src/darkfactory/model/_persistence.py`
  - Body references to `workflows/planning/workflow.py`, `prd.py`, and `builtins.py` updated to new module paths
  - Tool-allowlist Bash globs rewritten from `git add prds/:*` -> `git add .darkfactory/data/prds/:*` (and the matching `git diff`)
  - Narrative "stays inside prds/" updated to `.darkfactory/data/prds/`
  - AC-4 path reference updated from `prd.py` to `src/darkfactory/model/_persistence.py`
  - AC-6 path reference updated to `src/darkfactory/workflows/planning/workflow.py`
  - Bumped `updated` to 2026-04-11
- **Notes:** Core approach (template composition + forbidden_path_globs + set_blocks BuiltIn) is unchanged and still valid. Depends on PRD-227 and PRD-228 which are unrelated to PRD-622.

## PRD-540 — PyPI publishing
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal — release workflow and pyproject metadata. Zero overlap with data model refactor.

## PRD-543 — Harden harness create_pr step
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated from `src/darkfactory/builtins.py` -> `src/darkfactory/builtins/create_pr.py` and `src/darkfactory/builtins/push_branch.py`
  - Summary note added acknowledging builtins.py has been decomposed into the builtins/ package
  - Body references to `builtins.py` rewritten to point at the `builtins/` package / `builtins/_shared.py`
  - Bumped `updated` to 2026-04-11
- **Notes:** Core approach (capture stderr, merged-PR guard) is still valid. The builtins.py -> builtins/ split is PRD-549 (already in-progress / merged partially).

## PRD-545 — Harness-driven rebase and conflict resolution
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated: `builtins.py` -> `builtins/**`; `cli.py` -> `cli/**`
  - Prior-art reference updated from `src/darkfactory/cli.py` -> `src/darkfactory/cli/conflicts.py`
  - Bumped `updated` to 2026-04-11
- **Notes:** Substantive scheduler/rebase proposal is unaffected. Narrative references to PRD-549's `_legacy.py` workaround left intact since they describe historical incident context.

## PRD-546 — Impact declaration drift detection
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated `cli.py` -> `cli/**`
  - Body reference updated from `cli.py` subcommand -> `cli/check_drift.py` subcommand
  - Bumped `updated` to 2026-04-11
- **Notes:** Proposed drift history dir `.darkfactory/drift/` is a new (not-yet-created) location — left alone. Could potentially be `.darkfactory/data/drift/` for consistency with PRD-622's new layout; flagging for human review if a stronger opinion is wanted.

## PRD-547 — Cross-epic scheduler coordination
- **Impact:** none
- **Changes made:** none
- **Notes:** Only references new (proposed) modules `scheduler.py`, `registry.py`, `state.py`. No stale paths. Unaffected.

## PRD-550 — Upstream impact propagation
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated: `src/darkfactory/prd.py` -> `src/darkfactory/model/**`; `cli.py` -> `cli/**`; `prds/README.md` -> `.darkfactory/data/prds/README.md`
  - Bumped `updated` to 2026-04-11
- **Notes:** One in-body mention of `prds/README.md` left intact as an illustrative example.

## PRD-551 — Parallel graph execution
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated `src/darkfactory/cli.py` -> `src/darkfactory/cli/run.py`
  - Bumped `updated` to 2026-04-11
- **Notes:** Core parallel execution proposal is unaffected.
