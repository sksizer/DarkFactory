# PRD Impact Assessment — Post PRD-622 Data Model Refactor

**Date:** 2026-04-11
**Trigger:** PRD-622 (Data Model Refactor) merged to main as PR #171
**Method:** 9 parallel general-purpose subagents, each handling ~10 PRDs against the shared context brief at `.planning/impact-assessment-context.md`

## Scope

87 non-closed PRDs (statuses: `draft`, `ready`, `review`, `in-progress`, `blocked`) were assessed. PRD-622 itself and PRD-626 (assessed separately by the user) were excluded.

## Headline numbers

| Impact | Count | Notes |
|---|---:|---|
| **None** | 50 | Orthogonal to PRD-622 — left untouched |
| **Minor** | 32 | Stale module/path references fixed in place |
| **Major** | 1 | PRD-564 — half its scope already delivered |
| **Superseded** | 4 | Full scope delivered by PRD-622 or PRD-556 |

**Files edited:** 33 PRD markdown files. (4 of those are the superseded ones.)

## Newly superseded PRDs

| PRD | Title | Superseded by | Why |
|---|---|---|---|
| **PRD-601** | YAML date quoting consistency | PRD-622 | Deterministic serializer in `model/_persistence.py` enforces single-quoted dates and double-quoted wikilinks. `save()` is the single write path. |
| **PRD-625** | Archive Command | PRD-622 | `prd archive PRD-NNN` + `data/archive/` + `archive()` in `model/_persistence.py` all delivered. One semantic difference noted: PRD-622 uses terminal-status guardrails rather than blocking `in-progress`, and doesn't introduce a new `archived` status (archived PRDs keep their terminal status, distinguished only by disk location). |
| **PRD-600.2.4** | Single-source the package version | PRD-622 | `[tool.hatch.version]` in `pyproject.toml` reads `__version__` from `src/darkfactory/__init__.py`. |
| **PRD-600.2.7** | Delete dead cli stub file | PRD-556 (effectively) | `src/darkfactory/cli.py` is already gone after the cli/ package split. |

## Major-impact PRD (1)

### PRD-564 — Interactive init and path overrides

PRD-622 already delivered roughly half the original scope:
- `PathsConfig` exists on `Config`
- `.darkfactory/data/` layout is live
- `--prd-dir` was removed
- `cli.py` was split into `cli/` package
- `ensure_data_layout()` handles legacy migration

The agent rewrote requirements 6 and 10–14, the Technical Approach section, and added an explicit "what PRD-622 already delivered" header. Status left at `draft` because the interactive-prompting and user-configurable-override scope remains real work.

**🚩 Two new open questions added that need human review before this PRD is ready:**
1. How does `archive_dir` placement interact with a user-supplied `--data-dir` override?
2. How does interactive init compose with `ensure_data_layout()` when both legacy and new layouts are partially present?

## Minor-impact PRDs (32)

Almost all minor edits fall into one of these categories:

1. **Module path renames** — `src/darkfactory/prd.py` → `src/darkfactory/model/_prd.py` or `model/_persistence.py`. Imports like `from darkfactory.prd import` updated to `from darkfactory.model import`.
2. **CLI submodule paths** — `src/darkfactory/cli.py` (monolith) or `cli/__init__.py` updated to specific submodules like `cli/validate.py`, `cli/tree.py`, `cli/reconcile.py`, `cli/show.py`, etc. (post PRD-556 split).
3. **Data directory paths** — `.darkfactory/prds/` → `.darkfactory/data/prds/`.
4. **Workflow paths** — `workflows/...` → `src/darkfactory/workflows/...` (older PRDs predating the move).
5. **Function signature renames** — `prd_dir: Path` → `data_dir: Path` in proposed function signatures (e.g., PRD-600.4.1, PRD-600.4.2).

All edited PRDs had `updated` bumped to `'2026-04-11'`.

### Edited PRDs by batch

- **Batch 1 (10 PRDs, 7 minor):** 226, 229, 543, 545, 546, 550, 551
- **Batch 2 (10 PRDs, 4 minor):** 553, 554, 555, 558
- **Batch 3 (10 PRDs, 2 minor + 1 major):** 561, 562, 564 (major)
- **Batch 4 (10 PRDs, 2 minor):** 567.4, 567.4.1
- **Batch 5 (10 PRDs, 3 minor):** 600, 600.1.1, 600.1.2
- **Batch 6 (10 PRDs, 2 minor + 2 superseded):** 600.3.2, 600.3.3, 600.2.4 (superseded), 600.2.7 (superseded)
- **Batch 7 (10 PRDs, 7 minor):** 600.3.7, 600.3.9, 600.4, 600.4.1, 600.4.2, 600.4.3, 600.4.4
- **Batch 8 (10 PRDs, 1 minor + 1 superseded):** 602, 601 (superseded)
- **Batch 9 (7 PRDs, 1 minor + 1 superseded):** 616, 625 (superseded)

## Issues flagged for human review

1. **PRD-546 (impact drift detection)** — proposes `.darkfactory/drift/` as a new state directory. Consider nesting under `.darkfactory/data/drift/` for consistency with the new `data/` layout. (Agent left it alone since it's a new path, not a stale one.)

2. **PRD-556 (CLI modularization epic)** — structurally complete (`cli.py` is gone, all 25 submodules exist) but `status` was left as `in-progress` because PRD-556.18 (final cleanup) is still in `review` and the cleanup work (duplicate test files in `tests/test_cli_run.py` and `tests/test_cli_workflows.py`) is genuinely unfinished. Consider closing the epic once 556.18 merges.

3. **PRD-558 (auto-serialize sibling conflicts)** — confirmed NOT superseded by PRD-622's deterministic serializer. They solve different problems (execution-time ordering vs. file output). Path refs were updated.

4. **PRD-600.2** parent epic still lists `PRD-600.2.4-single-source-version` under `blocks:`. Now that 600.2.4 is superseded, the parent's `blocks` list should be pruned. The agent left the parent untouched to avoid pre-empting the sub-PRD's own assessment.

5. **PRD-605 (post-modularization cleanup)** — was blocked on PRD-556 (cli/ split) and PRD-622 (model/ split). Both are now merged and the issues described (unbounded `events` list in `cli/run.py`, `assign_cmd` comment mismatch) are still present. **Candidate to move from `blocked` → `ready`.** Agent did not flip the status because the brief said only touch `status` for truly superseded PRDs.

6. **PRD-616** had one stale `.darkfactory/prds/` reference in a prose section about manual commit recovery — fixed.

7. **PRD-621 (utils refactor)** — entirely orthogonal to PRD-622. PRD-622 touched `prd.py` → `model/` but left all external-service integration code (`git_ops.py`, `pr_comments.py`, `checks.py`, `invoke.py`, `utils/claude_code.py`, duplicated `_run_shell_once`) untouched. PRD-621 remains a clean follow-on applying the same module-per-concern principle PRD-622 established.

8. **PRD-567 epic** has one reference to `.darkfactory/prds/` but it's a historical incident quote (PRD-560 failure description). Left alone — quoting is correct in context.

## What was NOT touched

50 PRDs were left completely untouched as orthogonal:
- All of PRD-567.x except 567.4 and 567.4.1 (workflow reliability — invoke.py, runner.py, prompts, event log)
- Most of PRD-600.x (CI, ruff, pytest-cov, version flag, style.py tests, runner dedup, json flag warning, cleanup --yes, help text, loud workflow loading, prd show stub)
- All transcript/JSONL PRDs (PRD-559.x, 603, 604)
- All scheduling/parallelism PRDs (PRD-547, 551, 552, 570, 609)
- All agent-config and toolchain PRDs (PRD-607, 608, 610, 611, 612, 613)
- Git/PR builtins (PRD-618, 619)
- Older planning PRDs (PRD-225.7, 540, 541, etc.)
- Skill-creation PRDs (PRD-561, 562 — minor edits only)

## Next actions (recommended)

1. Merge this branch (`chore/prd-impact-assessment`) to capture the cleanup
2. Open PRD-605 from `blocked` → `ready`
3. Trim `PRD-600.2.4` from `PRD-600.2.blocks`
4. Discuss PRD-564's two new open questions before readying it
5. Decide on PRD-546 path placement (`.darkfactory/drift/` vs `.darkfactory/data/drift/`)
6. Close the PRD-556 epic once PRD-556.18 merges

## Per-batch reports

See `batch-01.md` through `batch-09.md` in this directory for the full per-PRD assessment from each subagent.
