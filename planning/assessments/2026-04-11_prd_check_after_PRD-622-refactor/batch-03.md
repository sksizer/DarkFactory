# Batch 3 — Impact Assessment

## PRD-561 — Establish a skill to help discuss and create detailed PRDs
- **Impact:** minor
- **Changes made:**
  - `impacts:` updated `src/darkfactory/cli.py` -> `src/darkfactory/cli/`
  - `.darkfactory/prds/` -> `.darkfactory/data/prds/` throughout (requirements, technical approach, ACs)
  - Technical Approach `prd init` section rewritten: `prd init` already exists and scaffolds `.darkfactory/data/prds/` + `.darkfactory/data/archive/`; this PRD now only adds the `.claude/commands/` bootstrap. Retargeted at `src/darkfactory/cli/init_cmd.py` + `src/darkfactory/init.py` instead of monolithic `cli.py`.
  - Removed requirement 7.c (creating `.darkfactory/prds/`) since PRD-622 already handles this.
  - Renumbered sub-items in requirement 7 after removal.
  - `updated` bumped to `'2026-04-11'`
- **Notes:** Core skill design is orthogonal and still valid.

## PRD-562 — Skill to triage draft PRDs and ready highest-impact one
- **Impact:** minor
- **Changes made:**
  - `.darkfactory/prds/` -> `.darkfactory/data/prds/` in Scan-phase requirement and References.
  - References: `src/darkfactory/prd.py` -> `src/darkfactory/model/` package (points at `model/_prd.py`, `model/_persistence.py`).
  - `updated` bumped to `'2026-04-11'`
- **Notes:** Skill design is orthogonal. No other stale refs.

## PRD-563 — Drain-ready-queue execution mode
- **Impact:** none
- **Changes made:** none
- **Notes:** No stale module paths, no `--prd-dir`, no `.darkfactory/prds/` refs. Extends PRD-220 graph execution conceptually; unaffected by PRD-622.

## PRD-564 — Interactive init and path overrides
- **Impact:** major
- **Changes made:**
  - Added explicit "Context — what PRD-622 already delivered" section explaining that `PathsConfig`, `.darkfactory/data/` layout, `ensure_data_layout()` migration, CLI split, and `--prd-dir` removal are all already done. Scoped remaining novel work to (1) interactive prompting and (2) user-configurable repo-relative overrides.
  - Default paths updated to `.darkfactory/data/prds/` throughout.
  - Requirement 6 rewritten: don't "add" `[paths]`, extend the existing `PathsConfig` to accept override keys from `config.toml`.
  - Added requirement 10 on archive_dir placement trade-off (flagged as open question).
  - Requirement 11-14 rewritten: discovery-side changes now target `src/darkfactory/config.py`, `src/darkfactory/paths.py`, and `cli/_shared.py` (not `discovery.py` + monolithic `cli.py`). Explicitly notes `--prd-dir` is not reintroduced; runtime override is `--directory` / `DARKFACTORY_DIR`.
  - Technical Approach for `config.py` / `paths.py` rewritten to extend the existing `PathsConfig` (with `project_dir`, `data_dir`, `prds_dir`, `archive_dir`) rather than add a new dataclass. Adds `workflows_dir` field and `resolve_paths()` helper signature.
  - Discovery-caller section rewritten: now describes `cli/main.py` / `cli/_shared.py` glue, flags the `load_all(data_dir)` call-site audit needed when `prds_dir` diverges from `data_dir/prds`.
  - ACs updated: AC-2 default path, AC-6 references `PathsConfig.resolves` instead of removed `resolved_prds()`, AC-8 replaced with "no `--prd-dir` reintroduction" constraint, AC-11 drops "lose to CLI flags" wording.
  - Added open questions 3 (archive_dir placement) and 4 (ensure_data_layout interaction with overrides).
  - Dependencies section now explicitly lists PRD-622 as prerequisite alongside PRD-222.
  - `impacts:` updated (`cli.py` -> `cli/init_cmd.py`, added `paths.py`).
  - `updated` bumped to `'2026-04-11'`
- **Notes:** About half of the original scope is now superseded by PRD-622. Remaining scope is meaningful: interactive prompts plus user-facing path overrides. Left in `draft` status — the remaining work is still real. Needs human review of open questions 3 and 4 before readying.

## PRD-567 — Workflow reliability improvements (epic)
- **Impact:** none
- **Changes made:** none
- **Notes:** Only stale-looking reference is a historical incident quote (`Write("/Users/.../DarkFactory/.darkfactory/prds/...")`) describing a PRD-560 failure. That reference is accurate as-of the incident and shouldn't be changed. Impacted-files list points at files that still exist (`graph_execution.py`, `templates_builtin.py`, `event_log.py`, etc.).

## PRD-567.1 — Worktree lifecycle resilience
- **Impact:** none
- **Changes made:** none
- **Notes:** Pure worktree/branch cleanup concern. Unaffected by PRD-622.

## PRD-567.1.1 — Extract safe-branch-cleanup helper
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `builtins/_shared.py`, which exists. No stale refs.

## PRD-567.1.2 — Ensure worktree auto-recovery
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `builtins/ensure_worktree.py`, which exists. No stale refs.

## PRD-567.1.3 — Pre-run stale cleanup
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `graph_execution.py` + `tests/test_graph_execution.py`, both exist. No stale refs.

## PRD-567.2 — Agent permission hygiene
- **Impact:** none
- **Changes made:** none
- **Notes:** Very short stub, no stale refs.
