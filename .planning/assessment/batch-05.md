# Batch 5 — Impact Assessment

## PRD-570 — Rename session_id to worker_id and emit worker lifecycle events
- **Impact:** none
- **Changes made:** none
- **Notes:** References `event_log.py`, `graph_execution.py`, `runner.py`, `cli/run.py` — all still valid paths. No references to `prd.py`, `.darkfactory/prds/`, `--prd-dir`, or `tmp_prd_dir`. Orthogonal to PRD-622.

## PRD-600 — Architectural Review and Code Quality Roadmap (epic)
- **Impact:** minor (preserved as historical snapshot)
- **Changes made:**
  - Bumped `updated` to 2026-04-11.
  - Added a "Snapshot note" callout near the top documenting that several findings have since been addressed: CLI god-module extraction (PRD-556), `prd.py` → `model/` package (PRD-622), directory layout change to `.darkfactory/data/`, archive command, deterministic serialization, version single-sourcing via `hatch.version` reading `__init__.py`. Noted that the high/critical safety items (reconcile recovery, shell-escape, setattr, ruff in CI) are still open.
- **Notes:** Per instructions I did not rewrite the analysis body; the LOC figures, section-2 tree, module LOC table, and hotspot descriptions are preserved as a 2026-04-09 snapshot. The callout directs readers to the current state.

## PRD-600.1 — Safety and correctness fixes (parent)
- **Impact:** none
- **Changes made:** none
- **Notes:** Parent PRD with only a summary + AC list. No stale code/module references. Sub-PRDs still accurately describe open work.

## PRD-600.1.1 — Add crash recovery to _create_reconcile_pr
- **Impact:** minor
- **Changes made:**
  - Bumped `updated` to 2026-04-11.
  - `impacts:` updated from `src/darkfactory/cli/__init__.py` to `src/darkfactory/cli/reconcile.py` (reconcile was extracted from the god module to its own file as part of PRD-556).
  - Summary prose updated to say "in `cli/reconcile.py`" with a parenthetical noting the extraction. Still has the crash-recovery gap.
  - Code location section updated: now points to `cli/reconcile.py` around line 112 (`_create_reconcile_pr`), describes the current `git_check`/`git_run` usage instead of bare `subprocess.run(check=True)`.
  - Edge case about `git branch -D` updated — current code already uses `git_check` which tolerates failure, so the "change to `check=False`" direction was rewritten.
  - AC-4 reworded accordingly; AC-5 updated to reference `cli/reconcile_test.py` (colocated peer test) rather than `tests/test_cli_reconcile.py`.
- **Notes:** Verified `_create_reconcile_pr` still has no `try/finally` — the fix is still open and still necessary.

## PRD-600.1.2 — Shell-escape user-controlled values in format_string
- **Impact:** minor
- **Changes made:**
  - Bumped `updated` to 2026-04-11.
  - Replaced the stale `prd.py:155` reference with `src/darkfactory/model/_prd.py` (the PRD dataclass lives in the model package now; `parse_prd` is in `model/_persistence.py`).
  - Consolidated the runner callsite bullets (line numbers from 2026-04-09 no longer map 1:1).
- **Notes:** Verified `workflow.py` still has `ExecutionContext.format_string` (line 272) and the shell-escape gap is still present. Approach (`shlex.quote`, `shell_escape=False` param option A) remains valid.

## PRD-600.1.3 — Remove setattr side channel in runner
- **Impact:** none
- **Changes made:** none
- **Notes:** Verified `runner.py` still has `setattr(ctx, "_last_agent_result", result)` at line 451 and `getattr(ctx, "_last_agent_result", None)` at line 243. `workflow.py:238` typed `last_invoke_result` field reference remains accurate. PRD is valid as-is.

## PRD-600.1.4 — Add ruff check and format check to CI
- **Impact:** none
- **Changes made:** none
- **Notes:** Verified `.github/workflows/ci.yml` currently runs only `uv run pytest` and `uv run mypy src tests` — still no ruff step, still no wheel build. PRD is fully valid and unchanged. (The batch brief flagged this as a "may already be done" check; it's NOT done.)

## PRD-600.2 — Tooling and CI hardening (parent)
- **Impact:** none (see note — needs human review)
- **Changes made:** none
- **Notes:** Parent lists PRD-600.2.4 (single-source version) under `blocks:`. PRD-622 already changed `[tool.hatch.version]` to read `src/darkfactory/__init__.py`, which was the core deliverable of 600.2.4. **Needs human review**: sub-PRD 600.2.4 (not in this batch) is likely superseded; the parent's blocks list may want pruning once that's confirmed. Did not touch the parent since the sub-PRD itself should be assessed first.

## PRD-600.2.1 — Configure comprehensive ruff rule set
- **Impact:** none
- **Changes made:** none
- **Notes:** Verified `pyproject.toml` has no `[tool.ruff]` or `[tool.ruff.lint]` section. Still fully valid.

## PRD-600.2.2 — Add pytest-cov and coverage reporting to CI
- **Impact:** none
- **Changes made:** none
- **Notes:** Verified `pyproject.toml` has no `[tool.coverage.*]` config and `pytest-cov` is not referenced. Still fully valid.
