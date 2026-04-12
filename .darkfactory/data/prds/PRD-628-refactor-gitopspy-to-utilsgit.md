---
id: PRD-628
title: Refactor git_ops.py to utils/git
kind: task
status: draft
priority: medium
effort: m
capability: simple
parent: null
depends_on: []
blocks: []
impacts: []
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-11'
tags: []
---

# Refactor git_ops.py to utils/git

## Summary

Move the three low-level subprocess primitives from the orphaned `git_ops.py` module into `utils/git/_run.py`, relocate the current `utils/git/__init__.py` helpers to `utils/git/_operations.py`, and update those helpers to use the new primitives. Update all 19 import sites and delete `git_ops.py`. This centralizes all git subprocess calls through a single gateway, enabling consistent error handling and a single place to evolve git call conventions.

## Motivation

`git_ops.py` is an orphaned module at the package root — it belongs in `utils/git/`, where git helpers already live. More importantly, `utils/git/__init__.py` currently calls `subprocess` directly, duplicating the subprocess wiring already in `git_ops.py`. Two parallel paths to run git commands means error handling, logging, and call conventions diverge silently. Consolidating everything in `utils/git/` under a single `_run.py` gateway gives one place to add structured error returns, logging, or timeout policy later.

## Requirements

### Functional

1. `git_check`, `git_run`, and `git_probe` move from `git_ops.py` to `utils/git/_run.py`.
2. The five helpers currently in `utils/git/__init__.py` (`diff_quiet`, `diff_show`, `status_other_dirty`, `run_add`, `run_commit`) move to `utils/git/_operations.py`.
3. `_operations.py` helpers that accept compatible signatures (`run_add`, `run_commit`, `diff_quiet`) are updated to use `_run.py` primitives instead of calling `subprocess` directly.
4. `utils/git/__init__.py` re-exports all public symbols from `_run.py` and `_operations.py` so existing callers of `from darkfactory.utils.git import ...` are unaffected.
5. All 19 `from darkfactory.git_ops import ...` call sites are updated to `from darkfactory.utils.git import ...` (or `from darkfactory.utils.git._run import ...` if importing within the package).
6. `git_ops.py` is deleted.

### Non-Functional

1. `mypy --strict` passes across all modified files.
2. Full test suite passes after the refactor.
3. Peer test file `utils/git/_run_test.py` exists (move or create alongside the new module).

## Technical Approach

**Resulting structure:**

```
utils/git/
  __init__.py       # re-exports from _run.py and _operations.py
  _run.py           # git_check, git_run, git_probe (moved from git_ops.py)
  _operations.py    # diff_quiet, diff_show, status_other_dirty, run_add, run_commit
  branch.py         # unchanged except imports: git_ops → utils.git._run
  worktree.py       # unchanged except imports: git_ops → utils.git._run
```

**Primitive usage in `_operations.py`:**

- `run_add(paths, cwd)` → `git_run("add", "--", *paths, cwd=cwd)`
- `run_commit(message, cwd)` → `git_run("commit", "-m", message, cwd=cwd)`
- `diff_quiet(paths, cwd)` → `git_check("diff", "--quiet", "--", *paths, cwd=cwd)`
- `status_other_dirty(paths, cwd)` → `git_run("status", "--porcelain", cwd=cwd)` then parse stdout (currently uses `check=False`; swap to `git_run` with exception handling or `git_check` pattern)
- `diff_show(paths, cwd)` — streams to terminal with no `capture_output`; see Open Questions

**Import migration:** All 19 sites importing `from darkfactory.git_ops import git_check, git_run, git_probe` change to `from darkfactory.utils.git import git_check, git_run, git_probe`. Callers within `utils/git/` (branch.py, worktree.py) should import from `._run` directly to avoid importing from their own package's `__init__.py`.

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/git_ops.py` does not exist.
- [ ] AC-2: `utils/git/_run.py` exists and exports `git_check`, `git_run`, `git_probe` with identical signatures.
- [ ] AC-3: `utils/git/_operations.py` exists and exports `diff_quiet`, `diff_show`, `status_other_dirty`, `run_add`, `run_commit`.
- [ ] AC-4: `utils/git/__init__.py` re-exports all public symbols; `from darkfactory.utils.git import diff_quiet, git_run` (etc.) still works.
- [ ] AC-5: `run_add`, `run_commit`, and `diff_quiet` in `_operations.py` use `_run.py` primitives — no direct `subprocess` calls for those three.
- [ ] AC-6: Zero occurrences of `from darkfactory.git_ops` in the codebase.
- [ ] AC-7: `mypy --strict` passes with no new errors.
- [ ] AC-8: `pytest` passes.

## Open Questions

- OPEN: `diff_show` streams git output directly to the terminal (no `capture_output`). `git_run` always captures. Options: (a) leave `diff_show` as a direct `subprocess.run` call since it's a display function, not an operation; (b) add a `git_stream(*args, cwd)` primitive to `_run.py` for terminal-visible git output. Decide before implementation.

- DEFERRED: Structured error returns (`Result[T, GitError]` or similar) — the `_run.py` module is now the right place to add this, but it is out of scope for this PRD. File a follow-up once the consolidation is done.

## References

- `src/darkfactory/git_ops.py` — source module being deleted
- `src/darkfactory/utils/git/__init__.py` — operations being moved to `_operations.py`
- `src/darkfactory/utils/git/branch.py` — internal caller, import needs updating
- `src/darkfactory/utils/git/worktree.py` — internal caller, import needs updating
