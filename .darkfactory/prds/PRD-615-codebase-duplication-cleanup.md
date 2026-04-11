---
id: PRD-615
title: Codebase duplication cleanup sweep
kind: feature
status: ready
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/cli/plan.py
  - src/darkfactory/cli/_shared.py
  - src/darkfactory/cli/children.py
  - src/darkfactory/cli/conflicts.py
  - src/darkfactory/cli/normalize.py
  - src/darkfactory/cli/rework.py
  - src/darkfactory/cli/run.py
  - src/darkfactory/cli/tree.py
  - src/darkfactory/cli/validate.py
  - src/darkfactory/cli/cleanup.py
  - src/darkfactory/cli/reconcile.py
  - src/darkfactory/cli/next_cmd.py
  - src/darkfactory/cli/status.py
  - src/darkfactory/cli/orphans.py
  - src/darkfactory/cli/undecomposed.py
  - src/darkfactory/cli/assign_cmd.py
  - src/darkfactory/cli/list_workflows.py
  - src/darkfactory/cli/system.py
  - src/darkfactory/builtins/_shared.py
  - src/darkfactory/builtins/commit.py
  - src/darkfactory/builtins/commit_transcript.py
  - src/darkfactory/builtins/commit_events.py
  - src/darkfactory/builtins/push_branch.py
  - src/darkfactory/builtins/create_pr.py
  - src/darkfactory/builtins/fetch_pr_comments.py
  - src/darkfactory/builtins/reply_pr_comments.py
  - src/darkfactory/builtins/ensure_worktree.py
  - src/darkfactory/builtins/cleanup_worktree.py
  - src/darkfactory/builtins/set_status.py
  - src/darkfactory/builtins/lint_attribution.py
  - src/darkfactory/builtins/rework_guard.py
  - src/darkfactory/builtins/analyze_transcript.py
  - src/darkfactory/builtins/system_builtins.py
  - src/darkfactory/event_log.py
  - src/darkfactory/config.py
  - src/darkfactory/prd.py
  - src/darkfactory/paths.py
  - src/darkfactory/checks.py
  - src/darkfactory/runner.py
  - tests/conftest.py
  - conftest.py
workflow: task
target_version:
created: 2026-04-11
updated: 2026-04-11
tags:
  - harness
  - quality
  - refactor
---

# Codebase duplication cleanup sweep

## Problem

A four-axis duplication audit (CLI commands, builtins, tests, and cross-cutting utilities) surfaced ~70 individual findings that consolidate into 13 actionable refactor candidates. Two are latent bug hazards; several represent the same root cause showing up across subpackages because the canonical helper either does not exist or is private.

The most painful patterns:

1. **Duplicate function definitions in `cli/plan.py`** that shadow `cli/_shared.py` — bug fixes to one copy will silently miss the other.
2. **Two identical 70-line `write_prd()` helpers** in `/conftest.py` and `tests/conftest.py` — schema drift waiting to happen.
3. **Three divergent git/subprocess patterns** (silent probe, log-and-fall-back, raise-on-fail) scattered across builtins and CLI commands with no unified wrapper.
4. **Dry-run shortcut** repeated verbatim in 15 builtin entry points.
5. **Event-writer emission boilerplate** repeated in 13+ sites with hand-built detail dicts.
6. **CLI integration test fixture sprawl** — `_init_git_repo()` reimplemented in 8 test files; `test_cli_run.py` alone has 17 tests with identical 6–8 line setup blocks; 12+ peer test files each define their own `_make_ctx()` MagicMock factory.
7. **PRD-by-id "unknown id" exit** repeated literally in 8 CLI commands.
8. **Worktree discovery near-duplicate** between `cli/cleanup.py` and `cli/rework.py` using two different strategies that probably handle different edge cases.

Total estimated payoff: ~700 lines of duplication eliminated and two latent bug hazards removed.

## Scope

In scope: the 13 candidates listed under Requirements below.

Out of scope:
- Unified exception hierarchy (`errors.py` with `DarkFactoryError` base) — pure hygiene, defer.
- Attribution-lint application consistency in builtins — separate behavior question, not duplication.
- Any new functionality. Every change must be behavior-preserving.

## Requirements

Refactors are grouped into themed PRs that should land in the suggested order. Each group is independently shippable.

### Group A — Critical bug hazards (do first)

1. **A1.** Delete the duplicate definitions of `_check_runnable` and `_resolve_base_ref` from `src/darkfactory/cli/plan.py` (lines 45–128). Import them from `cli/_shared.py` instead, matching the pattern in `cli/run.py`.
2. **A2.** Delete the duplicate `write_prd()` helper from `tests/conftest.py` (lines 37–106). Keep only the copy in root `conftest.py`; pytest's automatic fixture discovery makes the second copy redundant.

### Group B — High-impact shared helpers

3. **B1.** Create `src/darkfactory/git_ops.py` with three functions:
   - `git_check(*args, cwd) -> bool` — silent returncode probe.
   - `git_run(*args, cwd) -> CompletedProcess` — raises with rich `CalledProcessError` detail on non-zero exit.
   - `git_probe(*args, cwd, timeout=10) -> bool` — bounded probe with warn-and-fall-back on timeout.
   
   Migrate the following sites to the new helpers:
   - `builtins/push_branch.py:36-43`
   - `builtins/create_pr.py:102-109`
   - `builtins/reply_pr_comments.py:33-35`
   - `builtins/ensure_worktree.py:29-42, 52-79`
   - `builtins/commit.py:32-60`
   - `builtins/cleanup_worktree.py:33-46`
   - `cli/reconcile.py:17-37, 83-87`
   - `cli/cleanup.py:56-65`
   - `cli/rework.py:27-46`
   - `cli/rework_watch.py:139-170`
   
   Standardize on `cwd=` over `git -C <repo>` for clarity.

4. **B2.** Add `_log_dry_run(ctx, message: str) -> None` (or `_dry_run_or_continue(ctx, message) -> bool`) to `builtins/_shared.py`. Replace the `if ctx.dry_run: ...; return` block in:
   - `builtins/commit.py:27`
   - `builtins/cleanup_worktree.py:42`
   - `builtins/commit_transcript.py:41`
   - `builtins/commit_events.py:54`
   - `builtins/push_branch.py:24`
   - `builtins/ensure_worktree.py:101`
   - `builtins/create_pr.py:67`
   - `builtins/fetch_pr_comments.py:32`
   - `builtins/reply_pr_comments.py:76`
   - `builtins/set_status.py:25`
   - `builtins/lint_attribution.py:29`
   - `builtins/rework_guard.py:45`
   - `builtins/analyze_transcript.py:239`

5. **B3.** Add helper functions to `src/darkfactory/event_log.py`:
   - `emit_builtin_effect(ctx, task: str, effect: str, **detail) -> None`
   - `emit_dag(writer, ...) -> None` for the runner/graph_execution call sites.
   
   Each helper encodes the `if ctx.event_writer:` guard and documents the schema in its docstring (the docstrings serve as the de facto event registry). Migrate 13+ sites including `set_status.py:50`, `push_branch.py:46`, `commit.py:72`, `create_pr.py:118`, `reply_pr_comments.py:114`, `fetch_pr_comments.py:56`, `rework_guard.py:60, 78`, `runner.py:179, 212, 229, 262, 273, 464, 472`, `graph_execution.py:486`.

### Group C — Test fixture consolidation

6. **C1.** Add fixtures to `tests/conftest.py`:
   - `git_repo` — replaces the 8 hand-rolled `_init_git_repo()` definitions (`tests/test_cli_run.py:61`, `test_planning_workflow.py:84`, `test_plan_operation.py:18`, `test_cli_cleanup.py:25`, `test_cli_rework.py:24`, `test_planning_review_workflow.py:131`, `test_cli_system.py:17`, `test_cli_reconcile.py:17`).
   - `cli_project` — git + workflows_dir + prd_dir scaffold; replaces the 17 inline setup blocks in `test_cli_run.py` and similar in `test_planning_workflow.py`.
   - `make_prd` — factory fixture replacing `_make_prd()` in `test_runner.py:55` and `test_rework_workflow.py:242`.
   - `make_workflow` — factory replacing the 4 inconsistent local variants in `test_runner.py:37`, `test_assign.py:17`, `test_registry.py:22`, `test_rework_workflow.py:251`. Optional `with_prompts=True` flag for tests that need a prompts dir.
   - `make_execution_context` — factory replacing the 5 boilerplate ctx-creation blocks in `test_workflow.py:161` and `test_rework_workflow.py:138, 166, 191, 224`.

7. **C2.** Add a `make_builtin_ctx` factory (in `tests/conftest.py` or a new shared helper module) for the 12+ peer test files in `src/darkfactory/builtins/*_test.py` that each define their own MagicMock-based `_make_ctx()`. Migrate `commit_test.py`, `commit_transcript_test.py`, `ensure_worktree_test.py`, `push_branch_test.py`, `cleanup_worktree_test.py`, `set_status_test.py`, `lint_attribution_test.py`, `create_pr_test.py`, `reply_pr_comments_test.py`, `analyze_transcript_test.py`, etc.

### Group D — CLI shared helpers

8. **D1.** Add `_resolve_prd_or_exit(prd_id: str, prds: dict[str, PRD]) -> PRD` to `cli/_shared.py`. Replace the 8 instances of `if args.prd_id not in prds: raise SystemExit(...)` in `cli/children.py:13`, `conflicts.py:14`, `normalize.py:48`, `plan.py:139`, `rework.py:83`, `run.py:116`, `tree.py:54`, `validate.py:25-30`.

9. **D2.** Add to `cli/_shared.py`:
   - `_emit_json(payload: dict) -> int` — collapses the 12+ instances of `if args.json: print(json.dumps(payload, indent=2)); return 0`.
   - `_prd_to_dict(prd: PRD, fields: tuple[str, ...] = ...) -> dict` — replaces the near-identical PRD-to-dict payloads in `next_cmd.py:28`, `status.py:31`, `assign_cmd.py:40`.
   - `_format_prd_line(prd: PRD, fields: tuple[str, ...]) -> str` — collapses the 5 sites that print `f"{prd.id:14} [{attrs}]  {prd.title}"` with subtly different attribute selections (`children.py:20`, `orphans.py:15`, `undecomposed.py:26`, `next_cmd.py:48`, `status.py:61`).

### Group E — Cross-cutting helpers

10. **E1.** Make `config._load_toml()` public and add `config.load_section(section: str, fallback: str | None = None) -> dict` for the `[workflow.X]` → `[X]` fallback pattern. Migrate:
    - `builtins/analyze_transcript.py:59-71`
    - `builtins/commit_events.py:26-43`
    - `cli/run.py:36-47`

11. **E2.** Promote `runner._compute_branch_name()` to `prd.py` as public `compute_branch_name(prd) -> str`. Update `builtins/system_builtins.py:95` (currently has duplicate `_branch_name()`) and `checks.py:339` (currently inlines `f"prd/{prd_id}-{meta.slug}"`).

12. **E3.** Investigate then unify worktree discovery. `cli/cleanup.py:29-51` iterates `.worktrees/` and uses `checks._get_pr_state()`; `cli/rework.py:24-47` parses `git worktree list --porcelain`. Each strategy may handle edge cases (orphan branches, missing dirs) the other misses. Produce a single `find_worktree_for_prd(prd_id, repo_root) -> WorktreeInfo | None` helper that handles both, document the edge cases in its docstring, and migrate both call sites. **Investigate before merging** — the differences may indicate latent bugs.

13. **E4.** Add timestamp helpers (in a new `src/darkfactory/timestamps.py` or extend `paths.py`):
    - `today_iso() -> str` — `YYYY-MM-DD`
    - `now_iso_utc() -> str` — UTC, millisecond ISO-8601 with `Z` suffix (matches `event_log.py:37`)
    - `now_filename_safe() -> str` — hyphens-in-time form for filenames (matches `commit_transcript.py:42`)
    
    Migrate `prd.py:301, 316, 486`, `builtins/set_status.py:47`, `builtins/commit_transcript.py:42, 52`, `event_log.py:37`. Add path constants for `.worktrees/`, `.darkfactory/state/`, `.darkfactory/events/`, `.darkfactory/transcripts/` to `paths.py` while in the area.

## Technical Approach

Land as ~10 sequenced PRs roughly matching the groups above. Suggested order:

| PR | Groups | Effort | Notes |
|----|--------|--------|-------|
| 1  | A1 + A2 | 15 min | Critical hazards, no risk |
| 2  | D1 | 15 min | 8-site helper, easy review |
| 3  | B1 | 1 hr | `git_ops.py` — affects most builtins |
| 4  | B2 + B3 | 1 hr | Dry-run + event helpers in `_shared.py` / `event_log.py` |
| 5  | C1 | 2 hr | Bulk of test fixture consolidation |
| 6  | C2 | 1 hr | Peer-test ctx factory |
| 7  | E1 + E2 | 45 min | config + branch-name canonicalization |
| 8  | D2 | 50 min | CLI output helpers |
| 9  | E3 | 45 min | Worktree discovery — investigate first |
| 10 | E4 | 35 min | Timestamps + path constants |

Each PR must keep `just lint && just typecheck && just test` green. No test removed without proving the helper preserves coverage.

## Acceptance Criteria

- [ ] AC-1 (Group A): `cli/plan.py` no longer redefines `_check_runnable` or `_resolve_base_ref`; both are imported from `cli/_shared.py`. `tests/conftest.py` no longer defines `write_prd()` (only the root `conftest.py` does).
- [ ] AC-2 (Group B1): `src/darkfactory/git_ops.py` exists and exports `git_check`, `git_run`, `git_probe`. The 10+ migration sites listed in B1 use the new helpers; no direct `subprocess.run(["git", ...])` calls remain in `builtins/` or `cli/` outside of `git_ops.py` itself.
- [ ] AC-3 (Group B2): `builtins/_shared.py` exports a dry-run helper. None of the 13 migration sites in B2 contain a literal `if ctx.dry_run:` block.
- [ ] AC-4 (Group B3): `event_log.py` exports `emit_builtin_effect` (and any sibling helpers needed for runner/graph_execution sites). No `ctx.event_writer.emit(` calls remain in `builtins/`; runner.py and graph_execution.py go through the new helpers.
- [ ] AC-5 (Group C1): `tests/conftest.py` defines `git_repo`, `cli_project`, `make_prd`, `make_workflow`, and `make_execution_context` fixtures. No test file in `tests/` defines its own `_init_git_repo()`. `test_cli_run.py` test bodies use the `cli_project` fixture instead of inline 6–8 line scaffolds.
- [ ] AC-6 (Group C2): A `make_builtin_ctx` factory is reachable from peer tests in `src/darkfactory/builtins/*_test.py`. None of those peer tests define a local `_make_ctx()` MagicMock factory.
- [ ] AC-7 (Group D1): `cli/_shared.py` exports `_resolve_prd_or_exit`. The 8 migration sites in D1 use it. The literal string `unknown PRD id:` appears only inside `cli/_shared.py`.
- [ ] AC-8 (Group D2): `cli/_shared.py` exports `_emit_json`, `_prd_to_dict`, and `_format_prd_line`. The migration sites use them.
- [ ] AC-9 (Group E1): `config.py` exports public `load_toml` and `load_section`. The three migration sites in E1 use them.
- [ ] AC-10 (Group E2): `prd.py` exports `compute_branch_name`. `runner.py`, `system_builtins.py`, and `checks.py` all use it; no other module constructs `prd/{id}-{slug}` inline.
- [ ] AC-11 (Group E3): A single `find_worktree_for_prd` helper exists. `cli/cleanup.py` and `cli/rework.py` both use it. Investigation findings (which strategy handled which edge cases) are recorded in the helper's docstring.
- [ ] AC-12 (Group E4): A timestamps helper module exists and is used by the migration sites. `paths.py` exports constants for `.worktrees/`, `.darkfactory/state/`, `.darkfactory/events/`, `.darkfactory/transcripts/`.
- [ ] AC-13: `just lint && just typecheck && just test` pass at the head of each PR in the sequence and at the end of the sweep.
- [ ] AC-14: No behavioral change. Diffs should consist of (a) new helper modules/functions, (b) call-site migrations, (c) deletions of duplicated code. No new error messages, log lines, or exit codes that did not previously exist.

## Open Questions

- **OPEN — E3 worktree discovery:** Are the two existing strategies actually equivalent, or does each handle a case the other misses? Resolve during the E3 investigation; if they are not equivalent, the unified helper must preserve the union of edge cases.
- **OPEN — B3 event schema:** Should `emit_builtin_effect` accept `**detail` freely, or should detail keys be validated against a schema? Recommendation: accept freely for now (matches current behavior); revisit if event consumers grow brittle.
- **OPEN — C2 test factory location:** Should the builtin-ctx factory live in `tests/conftest.py` (cross-suite) or a new `src/darkfactory/builtins/_test_helpers.py` (peer-test-only)? Recommendation: `tests/conftest.py` if pytest's collection picks it up for peer tests; otherwise the peer-test helper module.

## References

- Audit conducted 2026-04-11 across four parallel sub-agent passes (CLI, builtins, tests, cross-cutting). Synthesis identified 13 candidates from ~70 individual findings.
