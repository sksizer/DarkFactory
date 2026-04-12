# Batch 9 — Impact Assessment

## PRD-612 — Agent-Assisted Toolchain Detection
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. Targets `cli/setup.py` and `toolchain/` — no references to `prd.py`, `.darkfactory/prds/`, `--prd-dir`, or old fixtures. Already written against the `cli/` package structure. Unaffected.

## PRD-613 — Agent Model Configuration and Fallback
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal to PRD-622. Impacts `invoke.py`, `runner.py`, `config.py`, `workflow.py`. Note: the PRD's proposed `[model]` config section predates PRD-622's `PathsConfig` expansion but does not conflict with it — they're separate config subsystems. No stale references to model persistence or PRD paths. Unaffected.

## PRD-616 — Interactive PRD discussion via phased Claude Code chain
- **Impact:** minor
- **Changes made:**
  - Quoted the `updated` date to `'2026-04-11'` to match the new canonical serialization format.
  - Updated a prose reference to the legacy PRD path in the "Commit step" section: `.darkfactory/prds/PRD-XXX-...md` → `.darkfactory/data/prds/PRD-XXX-...md`.
- **Notes:** PRD is already in `review` status. Module paths in `impacts:` already use the `cli/` package (`cli/discuss.py`, `cli/new.py`, etc.) and `commands/discuss/` subpackage. All Python imports in the body already reference `darkfactory.cli.discuss` (correct). The PRD talks about "the configured PRD directory" abstractly, which remains valid under PRD-622 (now resolved via `config.paths.prds_dir`). No approach-level changes needed — the discuss chain design is unaffected by the model refactor.

## PRD-618 — interactive sync_branch builtin
- **Impact:** none
- **Changes made:** none
- **Notes:** Purely about git branch sync behavior and `builtins/`. No references to the PRD data model, CLI flags, or paths affected by PRD-622. Unaffected.

## PRD-619 — decouple reply_pr_comments from push success
- **Impact:** none
- **Changes made:** none
- **Notes:** Orthogonal — targets `workflows/rework/workflow.py` and `runner.py` task-execution semantics. Line-number refs (`runner.py:242-245`) may drift over time but are not invalidated by PRD-622. Unaffected.

## PRD-621 — Refactor common functionality to util modules
- **Impact:** none
- **Changes made:** none
- **Notes:** Overlap check: PRD-622 decomposed `prd.py` into `model/` but did NOT touch `git_ops.py`, `pr_comments.py`, `checks.py`, `utils/git.py`, `invoke.py`, `utils/claude_code.py`, or the `_run_shell_once` duplication in `runner.py`/`system_runner.py`. PRD-621's entire scope remains untouched. The PRD's "module-per-concern with peer tests" approach is now explicitly reinforced by the CLAUDE.md architectural principles (PRD-622 established this pattern). No scope shift needed — PRD-621 is the natural follow-on applying the same decomposition pattern to external-service integration code. Unaffected.

## PRD-625 — Archive Command
- **Impact:** superseded
- **Changes made:**
  - Changed `status: ready` → `status: superseded`.
  - Quoted `updated` to `'2026-04-11'`.
  - Added a `## Superseded by` section near the top explaining that PRD-622 delivered the full scope: the `prd archive` CLI command (with stricter terminal-status + transitive-dep guardrails), the `data/archive/` folder, the `archive()` function in `model/_persistence.py`, and `load_all(include_archived=...)`.
  - Noted one semantic difference: PRD-622 does not introduce a new `archived` status — archived PRDs retain their terminal status (`done`/`superseded`/`cancelled`) and are distinguished by disk location only.
- **Notes:** This PRD's full technical approach was delivered verbatim by PRD-622. No further work remains.
