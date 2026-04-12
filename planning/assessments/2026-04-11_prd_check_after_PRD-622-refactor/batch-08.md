# Batch 8 — Impact Assessment

## PRD-601 — YAML date quoting consistency
- **Impact:** superseded
- **Changes made:**
  - Status flipped to `superseded`
  - Added `## Superseded by` section citing PRD-622's deterministic serializer in `model/_persistence.py` (`_format_scalar` single-quotes `date` objects and date-string patterns, double-quotes wikilinks; all writes go through `save()` using the same serializer)
  - Updated `impacts` entry `src/darkfactory/prd.py` -> `src/darkfactory/model/_persistence.py`
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Verified in `src/darkfactory/model/_persistence.py` lines 96-114 that date quoting is now unconditional.

## PRD-602 — Documentation site accuracy overhaul
- **Impact:** minor
- **Changes made:**
  - Added a "Module paths (post PRD-622 refactor)" subsection under Paths, documenting the new `darkfactory.model` package, `.darkfactory/data/prds/` and `.darkfactory/data/archive/` layout, removal of the `--prd-dir` flag, `PathsConfig`, and the new `prd archive` command
  - Added Requirements 4-6 covering module-path updates, the archive command, and deterministic serializer docs
  - Added matching acceptance-criteria bullets
  - Bumped `updated` to `'2026-04-11'`
- **Notes:** Status was already `review`; left unchanged. The docs themselves still need auditing against the new APIs/paths.

## PRD-603 — Transcript analysis robustness
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. Paths and module references (`builtins/analyze_transcript*.py`) are still accurate.

## PRD-604 — JSONL transcript validation
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal. `src/darkfactory/runner.py` is still the correct impact target.

## PRD-605 — Post-modularization code cleanup
- **Impact:** none
- **Changes made:** none
- **Notes:** Already references post-split paths (`cli/run.py`, `cli/assign_cmd.py`). Both issues (unbounded `events` list, assign_cmd comment mismatch) still present in current code per spot-check. This PRD can likely be unblocked since PRD-556 and PRD-622 are merged — flagged for human review.

## PRD-607 — Interactive Work Item Discovery
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal. Impact paths (`cli/main.py`, `discover.py`) still accurate; proposed new modules live under `darkfactory/` not `prd.py`.

## PRD-608 — Project Toolchain Setup Wizard
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. All impact paths still exist (`init.py`, `cli/main.py`, `runner.py`, `workflow.py`, `config.py`). `cli/setup.py` and `toolchain/` are proposed new modules — naming is consistent with current `cli/` package pattern.

## PRD-609 — Workflow Retry and Recovery Expansion
- **Impact:** none
- **Changes made:** none
- **Notes:** Rough draft braindump, orthogonal.

## PRD-610 — Agent Substitution for SDLC Slots
- **Impact:** none
- **Changes made:** none
- **Notes:** Rough draft, orthogonal.

## PRD-611 — Conditional SDLC Checks by File Path
- **Impact:** none
- **Changes made:** none
- **Notes:** Rough draft, orthogonal.
