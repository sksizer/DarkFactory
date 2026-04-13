---
id: PRD-633
title: Extract parameterized git primitives and subprocess containment test
kind: task
status: review
priority: high
effort: l
capability: complex
parent:
depends_on: []
blocks:
  - "[[PRD-631-system-operation-git-primitives]]"
impacts:
  - python/darkfactory/utils/
  - python/darkfactory/operations/ensure_worktree.py
  - python/darkfactory/operations/fast_forward_branch.py
  - python/darkfactory/operations/rebase_onto_main.py
  - python/darkfactory/operations/analyze_transcript.py
  - python/darkfactory/cli/reconcile.py
  - python/darkfactory/cli/rework_watch.py
  - python/darkfactory/cli/new.py
  - python/darkfactory/checks.py
  - python/darkfactory/graph/_impacts.py
  - python/darkfactory/rework/context.py
  - python/darkfactory/workflow/definitions/project/verify_merges/check.py
  - tests/test_subprocess_gateway.py
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-12
updated: 2026-04-12
tags:
  - architecture
  - refactor
  - testing
---

# Extract parameterized git primitives and subprocess containment test

## Summary

Extract reusable git primitives from workflow operations into `utils/git/`, route ALL `subprocess` calls outside `utils/` through gateway functions, and add a sentinel test enforcing that no subprocess calls exist outside `utils/`. Zero allowlist.

## Motivation

The workflow operations in `operations/` couple git business logic to `ExecutionContext`. PRD-631 needs to rewire these operations to accept a unified `RunContext`, which is much easier if the operations are already thin adapters over context-free primitives. Extracting first also makes the primitives independently testable.

Separately, several files bypass the `git_run()`/`gh_run()` gateways with direct `subprocess.run(["git", ...])` calls. PRD-615 (done) and PRD-628 (done) established the `utils/git/` and `utils/github/` structure with `git_run()`/`gh_run()` as the single subprocess gateways. PRD-621 (review, stalled) was supposed to finish migrating all callers but the migration was never completed and new direct calls have since appeared. A sentinel test codifies the single-gateway contract as an automated check so it cannot regress again.

## What Was Done

### Part 1: Extract `branch_exists_local` / `branch_exists_remote` to `utils/git/`

Moved `_branch_exists_local()` and `_branch_exists_remote()` from `operations/ensure_worktree.py` (where they were private helpers) to `utils/git/_operations.py` as public functions. Added re-exports in `utils/git/__init__.py`. Updated `ensure_worktree.py` to import from utils.

### Part 2: Convert operations to use `git_run()` gateway

**`operations/fast_forward_branch.py`** — 4 direct `subprocess.run` calls converted:
- `_fetch_origin_branch()`: try/except TimeoutExpired + stderr "couldn't find remote ref" → `git_run()` with match on `Ok`/`Timeout`/`GitErr` with stderr guard
- `_check_divergence()`: two calls (rev-parse verify + rev-list count) → `git_run()` with match
- `_get_head_sha()`: check=True pattern → `git_run()` with match + raise on GitErr

**`operations/rebase_onto_main.py`** — 5 direct `subprocess.run` calls converted:
- `_fetch_origin_main()`, `_get_sha()`, `_get_conflicting_files()`, rebase call, rebase abort — all converted to `git_run()` with pattern matching

**`operations/analyze_transcript.py`** — 2 calls converted:
- `subprocess.run(["git", "add", "-f", ...], check=True)` → `git_run("add", "-f", ...)` with match
- `subprocess.run(["pnpm", "dlx", "@anthropic-ai/claude-code", "--print", ...])` → `claude_print()` from `utils/claude_code/`

### Part 3: Convert CLI and other modules

**`cli/reconcile.py`** — 2 gh calls converted:
- `_get_merged_prd_prs()` → `gh_json()`, added `repo_root: Path` parameter
- `_create_reconcile_pr()` → `gh_run()` for PR creation

**`cli/rework_watch.py`** — 3 calls converted:
- `fetch_open_prd_prs()` → `gh_json()`, replaces try/except FileNotFoundError
- `_fetch_comment_ids()` → `gh_json()`, added `repo_root: Path` parameter, threaded through call chain
- `_trigger_rework()` → `run_foreground()` from `utils/shell.py`

**`rework/context.py`** — 1 gh call converted:
- `find_open_pr()` → `gh_json()`, replaces try/except block

**`checks.py`** — 1 git call converted:
- `SubprocessGitState.remote_branch_exists()` now delegates to `branch_exists_remote()` from utils/git

**`graph/_impacts.py`** — 1 git call converted:
- `tracked_files()` → `git_run("ls-files", ...)` with match

**`cli/new.py`** — 1 call converted:
- `subprocess.run([editor, str(path)])` → `run_foreground()` from `utils/shell.py`

**`workflow/definitions/project/verify_merges/check.py`** — 3 calls converted:
- `_run(["git", "merge-base", ...])` → `git_run()` with match
- `_run(["gh", "pr", "list", ...])` → `gh_json()` with match
- Removed standalone `_run()` wrapper

### Part 4: New gateway functions

**`utils/shell.py`** — added `run_foreground(cmd, *, cwd)` for running commands with terminal passthrough (no capture). Used by `cli/new.py` and `cli/rework_watch.py`.

**`utils/claude_code/_interactive.py`** — added `claude_print(prompt, *, model, cwd, ...)` for `--print` mode Claude Code invocations with captured output. Used by `operations/analyze_transcript.py`.

**`utils/github/__init__.py`** — added `gh_run` and `gh_json` to public re-exports.

### Part 5: Update all affected tests

Tests updated to mock at the gateway function level (`git_run`, `gh_json`) instead of `subprocess.run`. Return types changed from `CompletedProcess` to `Ok`/`GitErr`/`Timeout`/`GhErr`. Key test files updated:
- `fast_forward_branch_test.py` — 6 tests updated (mock target + return types)
- `rebase_onto_main_test.py` — 8 tests updated (consolidated dual git_run/subprocess mocks)
- `analyze_transcript_test.py` — mocks changed to git_run + claude_print
- `rework_watch_test.py` — gh mocks changed to gh_json
- `context_test.py` — 5 tests updated to mock gh_json
- `tests/test_checks.py` — 6 tests rewritten to mock `get_resume_pr_state` and `git_run` instead of global subprocess.run

### Part 6: Sentinel test

New test `tests/test_subprocess_gateway.py` — AST-scans all non-test `.py` files under `python/darkfactory/` and fails if ANY `subprocess.run`/`Popen`/`check_output` call exists outside `utils/`. No allowlist. Zero exceptions.

## Acceptance Criteria

- [x] AC-1: `branch_exists_local()`, `branch_exists_remote()` exist in `utils/git/` as context-free functions
- [x] AC-2: `operations/ensure_worktree.py` imports from `utils/git/` instead of defining locally
- [x] AC-3: `operations/fast_forward_branch.py` has zero direct `subprocess.run` calls
- [x] AC-4: `operations/rebase_onto_main.py` has zero direct `subprocess.run` calls
- [x] AC-5: `operations/analyze_transcript.py` has zero direct `subprocess` calls — git via `git_run()`, LLM via `claude_print()`
- [x] AC-6: `cli/reconcile.py` has zero direct `subprocess` calls — converted to `gh_json()`/`gh_run()`
- [x] AC-7: `cli/rework_watch.py` has zero direct `subprocess` calls — gh via `gh_json()`, self-invocation via `run_foreground()`
- [x] AC-8: `rework/context.py` has zero direct `subprocess` calls — converted to `gh_json()`
- [x] AC-9: `checks.py` has zero direct `subprocess` calls — delegates to `branch_exists_remote()`
- [x] AC-10: `graph/_impacts.py` has zero direct `subprocess` calls — converted to `git_run()`
- [x] AC-11: `cli/new.py` has zero direct `subprocess` calls — editor launch via `run_foreground()`
- [x] AC-12: `verify_merges/check.py` has zero direct `subprocess` calls — converted to `git_run()`/`gh_json()`
- [x] AC-13: Sentinel test exists and passes — zero `subprocess` calls outside `utils/`, no allowlist
- [x] AC-14: All existing tests pass (with mock targets updated to gateway functions)
- [x] AC-15: `mypy --strict` clean across all changed modules

## Relationship to PRD-621

PRD-621 ("Refactor common functionality to util modules", status: review) established the `utils/git/` and `utils/github/` package structure and defined AC-6: "zero occurrences of `subprocess.run(["gh"` outside `utils/github/`." That work stalled — the structure exists but the full migration was never completed. This PRD completes the migration for ALL subprocess calls across `python/darkfactory/` — not just git/gh but also Claude Code invocations, editor launches, and self-invocations — and adds a sentinel test enforcing that zero subprocess calls exist outside `utils/`.

## References

- `python/darkfactory/utils/git/_run.py` — `git_run()` gateway
- `python/darkfactory/utils/github/_cli.py` — `gh_run()` gateway
- `python/darkfactory/utils/git/_operations.py` — existing context-free helpers
- `python/darkfactory/utils/github/pr/__init__.py` — existing `create_pr()` helper
- [[PRD-615-codebase-duplication-cleanup]] — established the duplication cleanup that led to utils extraction
- [[PRD-621-refactor-common-functionality-in-regards-to-external-systems-services-commands-to-util-modules]] — partially completed subprocess consolidation (review, stalled)
- [[PRD-628-refactor-gitopspy-to-utilsgit]] — moved `git_ops.py` to `utils/git/`
- [[PRD-631-system-operation-git-primitives]] — depends on this work for RunContext unification
