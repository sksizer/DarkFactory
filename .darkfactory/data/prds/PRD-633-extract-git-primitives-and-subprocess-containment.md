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
  - src/darkfactory/utils/git/
  - src/darkfactory/utils/github/
  - src/darkfactory/operations/ensure_worktree.py
  - src/darkfactory/operations/fast_forward_branch.py
  - src/darkfactory/operations/rebase_onto_main.py
  - src/darkfactory/operations/analyze_transcript.py
  - src/darkfactory/cli/reconcile.py
  - src/darkfactory/cli/rework_watch.py
  - src/darkfactory/checks.py
  - src/darkfactory/graph/_impacts.py
  - src/darkfactory/rework/context.py
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

Extract reusable git primitives from workflow operations into `utils/git/`, convert all direct `subprocess.run(["git"/"gh", ...])` calls outside the gateway layer to use `git_run()`/`gh_run()`/`gh_json()`, and add a sentinel test enforcing the single-gateway contract.

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

**`operations/analyze_transcript.py`** — 1 git call converted:
- `subprocess.run(["git", "add", "-f", ...], check=True)` → `git_run("add", "-f", ...)` with match

### Part 3: Convert CLI and other modules

**`cli/reconcile.py`** — 2 gh calls converted:
- `_get_merged_prd_prs()` → `gh_json()`, added `repo_root: Path` parameter
- `_create_reconcile_pr()` → `gh_run()` for PR creation

**`cli/rework_watch.py`** — 2 gh calls converted:
- `fetch_open_prd_prs()` → `gh_json()`, replaces try/except FileNotFoundError
- `_fetch_comment_ids()` → `gh_json()`, added `repo_root: Path` parameter, threaded through call chain

**`rework/context.py`** — 1 gh call converted:
- `find_open_pr()` → `gh_json()`, replaces try/except block

**`checks.py`** — 1 git call converted:
- `SubprocessGitState.remote_branch_exists()` now delegates to `branch_exists_remote()` from utils/git

**`graph/_impacts.py`** — 1 git call converted:
- `tracked_files()` → `git_run("ls-files", ...)` with match

### Part 4: Re-export `gh_run` / `gh_json` from `utils/github/__init__.py`

Added `gh_run` and `gh_json` to the public re-exports so callers outside the package don't need to import from private `_cli` module.

### Part 5: Update all affected tests

Tests updated to mock at the gateway function level (`git_run`, `gh_json`) instead of `subprocess.run`. Return types changed from `CompletedProcess` to `Ok`/`GitErr`/`Timeout`/`GhErr`. Key test files updated:
- `fast_forward_branch_test.py` — 6 tests updated (mock target + return types)
- `rebase_onto_main_test.py` — 8 tests updated (consolidated dual git_run/subprocess mocks)
- `analyze_transcript_test.py` — split mock for git_run vs subprocess.run (pnpm)
- `rework_watch_test.py` — gh mocks changed to gh_json
- `context_test.py` — 5 tests updated to mock gh_json
- `tests/test_checks.py` — 6 tests rewritten to mock `get_resume_pr_state` and `git_run` instead of global subprocess.run

### Part 6: Sentinel test

New test `tests/test_subprocess_gateway.py` with two assertions:
1. **No violations** — AST-scans all non-test `.py` files under `src/darkfactory/`, flags any `subprocess.run`/`Popen`/`check_output` call with `git` or `gh` as first arg outside the gateways
2. **Allowlist freshness** — every bypass-allowlisted file still contains a subprocess call (prevents stale allowlist entries)

**Gateway files** (where subprocess calls are expected):
- `utils/git/_run.py` — `git_run()` gateway
- `utils/github/_cli.py` — `gh_run()`/`gh_json()` gateway

**Bypass allowlist** (2 entries):
- `utils/git/_operations.py` — `diff_show()` terminal passthrough (no `capture_output`)
- `workflow/definitions/project/verify_merges/check.py` — standalone `__main__` script

## Acceptance Criteria

- [x] AC-1: `branch_exists_local()`, `branch_exists_remote()` exist in `utils/git/` as context-free functions
- [x] AC-2: `operations/ensure_worktree.py` imports from `utils/git/` instead of defining locally
- [x] AC-3: `operations/fast_forward_branch.py` has zero direct `subprocess.run` calls
- [x] AC-4: `operations/rebase_onto_main.py` has zero direct `subprocess.run` calls
- [x] AC-5: `operations/analyze_transcript.py` git call converted to `git_run()`
- [x] AC-6: `cli/reconcile.py` has zero direct `subprocess` calls — converted to `gh_json()`/`gh_run()`
- [x] AC-7: `cli/rework_watch.py` gh calls converted to `gh_json()`
- [x] AC-8: `rework/context.py` converted to `gh_json()`
- [x] AC-9: `checks.py` delegates to `branch_exists_remote()` from utils/git
- [x] AC-10: `graph/_impacts.py` converted to `git_run()`
- [x] AC-11: Sentinel test exists and passes — no direct git/gh subprocess calls outside gateways (beyond 2-entry bypass allowlist)
- [x] AC-12: Sentinel test validates allowlist freshness — every allowlisted file still contains a violation
- [x] AC-13: All existing tests pass (with mock targets updated to gateway functions)
- [x] AC-14: `mypy --strict` clean across all changed modules

## Relationship to PRD-621

PRD-621 ("Refactor common functionality to util modules", status: review) established the `utils/git/` and `utils/github/` package structure and defined AC-6: "zero occurrences of `subprocess.run(["gh"` outside `utils/github/`." That work stalled — the structure exists but the full migration was never completed. This PRD completes the migration for all git/gh subprocess calls across `src/darkfactory/` and adds the sentinel test that PRD-621 lacked.

## References

- `src/darkfactory/utils/git/_run.py` — `git_run()` gateway
- `src/darkfactory/utils/github/_cli.py` — `gh_run()` gateway
- `src/darkfactory/utils/git/_operations.py` — existing context-free helpers
- `src/darkfactory/utils/github/pr/__init__.py` — existing `create_pr()` helper
- [[PRD-615-codebase-duplication-cleanup]] — established the duplication cleanup that led to utils extraction
- [[PRD-621-refactor-common-functionality-in-regards-to-external-systems-services-commands-to-util-modules]] — partially completed subprocess consolidation (review, stalled)
- [[PRD-628-refactor-gitopspy-to-utilsgit]] — moved `git_ops.py` to `utils/git/`
- [[PRD-631-system-operation-git-primitives]] — depends on this work for RunContext unification
