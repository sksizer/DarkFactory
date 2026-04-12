# Batch 2 — Impact Assessment

## PRD-552 — Merge-upstream task for PRDs with multiple dependencies
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. References `src/darkfactory/builtins/merge_upstream.py`, `src/darkfactory/runner.py`, and `tests/test_merge_upstream.py` — none of these are stale. The `workflows/` reference in the body is generic ("Agent prompt template lives under `workflows/`") and not worth churning for.

## PRD-553 — Make "create child PRDs" an explicit task-level permission
- **Impact:** minor
- **Changes made:**
  - Updated `impacts:` entry `workflows/planning/workflow.py` → `src/darkfactory/workflows/planning/workflow.py`
  - Body: `prds/**` → `.darkfactory/data/prds/**` in requirements 2 and 3
  - Requirement 4 and References: `workflows/planning/workflow.py` → `src/darkfactory/workflows/planning/workflow.py`
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Approach remains valid; only path references were stale.

## PRD-554 — Harden the planning workflow prompts
- **Impact:** minor
- **Changes made:**
  - `impacts:` frontmatter list rewritten to `src/darkfactory/workflows/planning/...` paths (was `workflows/planning/...`)
  - Body prose (summary, requirement 5b, 6, AC-3, open questions, References) updated `workflows/planning/` → `src/darkfactory/workflows/planning/` and `prds/` → `.darkfactory/data/prds/` consistently
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Approach and prompts content unchanged; only directory path references were stale. Workflows live under `src/darkfactory/workflows/`, not a top-level `workflows/` dir.

## PRD-555 — backlog_review workflow
- **Impact:** minor
- **Changes made:**
  - `impacts:` replaced stale `workflows/backlog_review/...` entries with `src/darkfactory/workflows/backlog_review/...`
  - `impacts:` replaced `src/darkfactory/cli.py` with `src/darkfactory/cli/review_backlog.py`, `src/darkfactory/cli/review_backlog_test.py`, `src/darkfactory/cli/_parser.py` (CLI is now a package post-PRD-556)
  - Body: workflow-shape section path corrected; added explicit note that CLI is modularized and the new subcommand lives at `cli/review_backlog.py` with peer test
  - Tool allowlist section: `prds/**` → `.darkfactory/data/prds/**`
  - AC-1: `workflows/backlog_review/` → `src/darkfactory/workflows/backlog_review/`
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Overall approach still valid.

## PRD-556 — Split src/darkfactory/cli.py into a package
- **Impact:** none (notable but no file edits)
- **Changes made:** none
- **Notes:** Status remains `in-progress` because PRD-556.18 (final cleanup) is still `review`. Structurally complete: `cli.py` the file is gone, all submodules (`new.py`, `status.py`, `validate.py`, `tree.py`, `children.py`, `orphans.py`, `undecomposed.py`, `conflicts.py`, `list_workflows.py`, `assign_cmd.py`, `normalize.py`, `plan.py`, `run.py`, `reconcile.py`, `next_cmd.py`, `cleanup.py`, `rework.py`, `rework_watch.py`, `system.py`, `discuss.py`, `init_cmd.py`, `archive.py`, `_parser.py`, `_shared.py`, `main.py`) exist under `src/darkfactory/cli/`. The historical "1423 lines, 14 subcommand implementations" note is intentional as written — it describes pre-work state. Not touching since the epic is naturally concluding through its final-cleanup child. **Flag for human review:** consider closing this epic once PRD-556.18 merges.

## PRD-556.18 — Final cleanup
- **Impact:** none
- **Changes made:** none
- **Notes:** Still valid. `tests/test_cli_run.py` and `tests/test_cli_workflows.py` both still exist in the tree, so the cleanup is genuinely unfinished. Status is `review`.

## PRD-557 — Split src/darkfactory/runner.py
- **Impact:** none
- **Changes made:** none
- **Notes:** `src/darkfactory/runner.py` still exists as a single module. The PRD's approach is unaffected by PRD-622.

## PRD-558 — Auto-serialize sibling PRDs with overlapping impacts
- **Impact:** minor
- **Changes made:**
  - `impacts:` `src/darkfactory/cli.py` → `src/darkfactory/cli/_parser.py` and `src/darkfactory/cli/run.py` (CLI is a package now)
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Body mentions "PRD-556 has 18 children" and "18-way fan-out" — these are historical references to PRD-556's decomposition, not stale for PRD-622 purposes. The deterministic serializer that PRD-622 introduced does **not** supersede this PRD — PRD-558 is about serializing execution order to avoid merge conflicts, a different problem from deterministic frontmatter output. Approach still valid; pick-an-option is still open.

## PRD-559.4 — Implement analyze_transcript builtin entry point
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. References `src/darkfactory/builtins/analyze_transcript.py`, `analyze_transcript_test.py`, and `builtins/__init__.py` — all correct.

## PRD-559.5 — Integrate analyze_transcript into workflows
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. Impact paths (`src/darkfactory/workflows/{default,planning,extraction}/workflow.py`) are all current.
