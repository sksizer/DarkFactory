---
id: "PRD-504"
title: "Update CLI defaults for standalone darkfactory operation"
kind: task
status: done
priority: high
effort: s
capability: moderate
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on:
  - "[[PRD-503-darkfactory-port-tests-workflows]]"
blocks:
  - "[[PRD-505-darkfactory-verify-and-push]]"
impacts:
  - (darkfactory repo) python/darkfactory/cli.py
  - (darkfactory repo) tests/test_cli_workflows.py
  - (darkfactory repo) tests/test_cli_run.py
  - (darkfactory repo) prds/**
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - extraction
  - cli
---

# Update CLI defaults for standalone darkfactory operation

## Summary

The harness currently hardcodes pumice-specific paths: `_default_prd_dir()` looks for `docs/prd/` and `_default_workflows_dir()` looks for `tools/prd-harness/workflows/`. In the standalone darkfactory layout, `--prd-dir` should default to `prds/` at the repo root and `--workflows-dir` should default to `workflows/` at the repo root.

Also move the dev-PRDs from `tools/prd-harness/dev-prds/` into `darkfactory/prds/` (renamed location) so the harness has PRDs to drive its own future work.

## Requirements

1. `_default_prd_dir()` in `cli.py` returns `<repo_root>/prds/` (was `<repo_root>/docs/prd/`).
2. `_default_workflows_dir()` returns `<repo_root>/workflows/` (was `<repo_root>/tools/prd-harness/workflows/`).
3. `_find_repo_root()` is unchanged — it still walks up looking for `.git`.
4. All dev-PRDs from `tools/prd-harness/dev-prds/PRD-*.md` are copied into `darkfactory/prds/` (minus the user's collision drafts `PRD-300-*.md` and `PRD-400-*.md` which are unfinished).
5. `darkfactory/prds/README.md` carries a short note explaining the PRD set.
6. After the move, `uv run prd status` (from within darkfactory) correctly reads the 12 migrated dev-PRDs.
7. `uv run prd list-workflows` shows `default`.
8. `uv run prd plan PRD-201` returns a sensible plan output.

## Technical Approach

Two small edits to `cli.py`:

```python
def _default_prd_dir() -> Path:
    """Locate prds/ at the repo root."""
    repo = _find_repo_root(Path.cwd())
    return repo / "prds"


def _default_workflows_dir() -> Path:
    """Locate workflows/ at the repo root."""
    repo = _find_repo_root(Path.cwd())
    return repo / "workflows"
```

Then migrate the PRD files:

```bash
mkdir -p ~/Developer/darkfactory/prds
cp tools/prd-harness/dev-prds/PRD-{200,201,202,203,204,205,206,207,208,209,210,211}*.md \
   ~/Developer/darkfactory/prds/
cp tools/prd-harness/dev-prds/PRD-500*.md \
   ~/Developer/darkfactory/prds/
# Write a short prds/README.md
```

No test updates needed — `test_cli_workflows.py` and `test_cli_run.py` both use fixture directories via `--prd-dir`/`--workflows-dir` overrides, not the defaults.

## Acceptance Criteria

- [ ] AC-1: `_default_prd_dir()` returns `<repo_root>/prds/`.
- [ ] AC-2: `_default_workflows_dir()` returns `<repo_root>/workflows/`.
- [ ] AC-3: `darkfactory/prds/` contains the 12 ported task PRDs (PRD-200..211) plus the extraction PRDs (PRD-500..505, 510, 520).
- [ ] AC-4: `uv run prd status` (from within darkfactory) reports the correct counts.
- [ ] AC-5: `uv run prd tree PRD-200` shows the workflow execution layer tree.
- [ ] AC-6: `uv run prd plan PRD-201` prints a plan with the default workflow.
- [ ] AC-7: All tests still pass after the cli.py changes.

## References

- [[PRD-503-darkfactory-port-tests-workflows]] — dependency
- [[PRD-505-darkfactory-verify-and-push]] — next step
