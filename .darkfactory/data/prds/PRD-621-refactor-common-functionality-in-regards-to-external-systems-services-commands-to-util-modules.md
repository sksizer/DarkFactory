---
id: PRD-621
title: Refactor common functionality in regards to external systems, services, commands to util modules
kind: task
status: ready
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: 2026-04-11
tags: []
---

# Refactor common functionality in regards to external systems, services, commands to util modules

## Summary

Consolidate scattered subprocess interactions with Git, GitHub CLI, and Claude Code into well-structured `utils/` package directories (`utils/git/`, `utils/github/`, `utils/claude_code/`). Update all call sites directly — no shims or re-exports at old locations.

## Motivation

External system interactions (git, gh, claude) are spread across top-level modules (`git_ops.py`, `pr_comments.py`, `checks.py`) and builtins with duplicated subprocess patterns and inconsistent error handling. `utils/git.py` calls `subprocess.run` directly instead of using the primitives in `git_ops.py`. GitHub CLI calls are scattered across 4+ modules with no shared foundation.

Restructuring into focused package directories improves tree visibility, makes it easier to find and extend external system code, and reduces duplication. This is a maintainability and scalability investment.

## Requirements

### Functional

1. Create `utils/git/` package: merge `git_ops.py` primitives (`git_run`, `git_check`, `git_probe`) and `utils/git.py` convenience wrappers into a single package. Refactor convenience wrappers to use the `git_ops` primitives (`git_run`, `git_check`) instead of calling `subprocess.run` directly. Re-export public API from `__init__.py`.
2. Create `utils/github/` package with focused modules:
   - `_cli.py` — low-level `gh` subprocess wrapper (parallel to git primitives)
   - `pull_request.py` — PR state queries, PR creation
   - `comments.py` — review thread fetching, comment posting (subprocess bits extracted from `pr_comments.py`)
3. Consolidate `utils/claude_code.py` into `utils/claude_code/` package (move existing `spawn_claude` plus `invoke.py` subprocess logic).
4. Extract shared shell runner helper from the duplicated `_run_shell_once` in `runner.py` and `system_runner.py` into a common utility accepting `cwd: Path` directly. The two implementations are functionally identical — both merge `os.environ` with a passed `env` dict and call `subprocess.run(cmd, shell=True, cwd=..., capture_output=True, text=True, check=False)`. The only difference is the context type parameter (`ExecutionContext` vs `SystemContext`), which is resolved by accepting `cwd: Path` instead.
5. Update all call sites to import from new locations. No shims or re-exports at old paths — delete the old modules.
6. Business logic in `pr_comments.py` (filtering, threading, agent reply parsing) stays in place. Specific split:
   - `_gh_repo_nwo()` moves to `utils/github/_cli.py` (clean wrapper, no business logic)
   - `_gh_fetch()` is split: the raw GraphQL subprocess call moves to `utils/github/_cli.py`; the response reshaping logic stays in `pr_comments.py`
   - `post_comment_replies()` stays in `pr_comments.py` (heavy orchestration logic) but calls through `utils/github/_cli.py` for the raw `gh api POST`
   - `_resolve_commit_timestamp()` moves to `utils/git/` (clean `git log` wrapper)

### Non-Functional

1. All existing tests pass without modification (beyond import path updates).
2. mypy strict continues to pass.
3. No new runtime dependencies.

## Technical Approach

### Target structure

```
src/darkfactory/
  utils/
    git/
      __init__.py          # re-exports: git_run, git_check, git_probe, diff_quiet, etc.
      _ops.py              # primitives from git_ops.py
      _diff.py             # diff_quiet, diff_show
      _staging.py          # run_add, run_commit, status_other_dirty
    github/
      __init__.py          # re-exports public API
      _cli.py              # low-level gh subprocess wrapper
      pull_request.py      # PR state queries, creation
      comments.py          # review thread fetch, comment posting
    claude_code/
      __init__.py          # re-exports: invoke_claude, spawn_claude, InvokeResult
      _interactive.py      # spawn_claude() from current utils/claude_code.py
      _invoke.py           # invoke_claude(), InvokeResult, capability_to_model() from invoke.py
    shell.py               # shared _run_shell_once(cmd, cwd, env)
```

### Migration

One package per commit — 4 atomic commits. Each commit: create package, move code, update all call sites, delete old module. Before each old-module deletion, verify `grep -r "from darkfactory.<old_module>" src/` returns zero matches.

**Commit 1 — `utils/git/`:**
- `git_ops.py` (top-level) → `utils/git/_ops.py`, then delete `git_ops.py`
- `utils/git.py` → split into `utils/git/_diff.py` and `utils/git/_staging.py`, refactored to use `_ops` primitives
- `_resolve_commit_timestamp()` from `pr_comments.py` → `utils/git/`
- 15+ call sites updated from `from darkfactory.git_ops import ...` to `from darkfactory.utils.git import ...`

**Commit 2 — `utils/github/`:**
- `_gh_repo_nwo()` from `pr_comments.py` → `utils/github/_cli.py`
- `_gh_fetch()` split: raw GraphQL call → `utils/github/_cli.py`; reshaping stays in `pr_comments.py`
- `post_comment_replies()` stays but calls through `utils/github/_cli.py` for `gh api POST`
- `checks.py` gh calls (`_get_pr_state`, `_fetch_all_pr_states`) → `utils/github/pull_request.py`
- `builtins/create_pr.py` gh calls → `utils/github/pull_request.py`

**Commit 3 — `utils/claude_code/`:**
- `utils/claude_code.py` → `utils/claude_code/_interactive.py`
- `invoke.py` → `utils/claude_code/_invoke.py`
- Update importers of `invoke_claude`, `InvokeResult`, `spawn_claude`

**Commit 4 — `utils/shell.py`:**
- Extract `_run_shell_once` from `runner.py` and `system_runner.py` into `utils/shell.py`
- Both callers updated to import from `utils.shell` and pass `ctx.cwd`

## Acceptance Criteria

- [ ] AC-1: `git_ops.py` (top-level) and `utils/git.py` (flat file) are deleted; all git subprocess logic lives in `utils/git/` package
- [ ] AC-2: `utils/github/` package exists with `_cli.py`, `pull_request.py`, and `comments.py`; no direct `gh` subprocess calls remain outside this package
- [ ] AC-3: `utils/claude_code/` package consolidates Claude Code subprocess logic
- [ ] AC-4: Duplicated `_run_shell_once` is extracted to a shared utility; both runners use it
- [ ] AC-5: All existing tests pass, mypy strict passes, ruff passes
- [ ] AC-6: No shims or re-exports at old module paths — old files are deleted

## Open Questions

- RESOLVED: Shims at old import paths? — No, update all call sites directly.
- RESOLVED: Target structure for git? — `utils/git/` package directory with focused sub-modules.
- RESOLVED: Should `checks.py` `SubprocessGitState` move into `utils/git/`? — No. `SubprocessGitState` only makes `git` calls (`git ls-remote`), not `gh` calls. The `gh` calls in `checks.py` are in separate standalone functions (`_get_pr_state`, `_fetch_all_pr_states`) that move cleanly to `utils/github/pull_request.py` without touching the Protocol. `SubprocessGitState` stays in `checks.py` — tightly coupled to the checks domain, no reuse elsewhere.
- RESOLVED: Does AC-2 ("no `gh` calls outside `utils/github/`") require changes to tests or `builtins/reply_pr_comments.py`? — No. `reply_pr_comments.py` delegates to `pr_comments.py` with no direct `gh` calls. All tests mock at the function boundary, not at subprocess level. AC-2 holds as-written.

## References

- `src/darkfactory/git_ops.py` — current git primitives (15+ importers)
- `src/darkfactory/utils/git.py` — current git convenience wrappers
- `src/darkfactory/pr_comments.py` — GitHub comment logic (~500 lines)
- `src/darkfactory/checks.py` — PR state checks
- `src/darkfactory/runner.py:557-576` — shell runner (duplicated)
- `src/darkfactory/system_runner.py:356-373` — shell runner (duplicate)

## Assessment (2026-04-11)

- **Value**: 3/5 — pure maintenance investment. No user-visible
  feature, but the downstream payoff is real: PRD-600.3.1 becomes
  trivial, PRD-600.1.2 has a cleaner place to add the shell-escape
  seam, and future builtins that need GitHub CLI access get a shared
  helper instead of copy-pasting subprocess patterns.
- **Effort**: s — dropped from `m` because `utils/git.py`,
  `utils/system.py`, `utils/claude_code.py`, `utils/terminal.py`, and
  `utils/tui.py` already exist as flat files. The main work is to
  re-nest them into package directories, split `pr_comments.py`'s
  `gh` calls into `utils/github/`, and extract `_run_shell_once`
  to `utils/shell.py`. The call-site updates are mechanical.
- **Current state**: partially landed. `src/darkfactory/utils/`
  exists but flat; target structure is per-package (`utils/git/`,
  `utils/github/`, `utils/claude_code/`). `git_ops.py`,
  `pr_comments.py`, and `invoke.py` are still top-level. The
  duplicate `_run_shell_once` still lives in both `runner.py:591` and
  `system_runner.py` (the line numbers in this PRD's References are
  off by ~34 — not blocking but worth fixing).
- **Gaps to fully implement**:
  - **Commit 1** — `utils/git/` package: move `git_ops.py` →
    `utils/git/_ops.py`, split `utils/git.py` into `_diff.py` /
    `_staging.py`, update ~15 call sites, delete `git_ops.py`.
  - **Commit 2** — `utils/github/` package: create `_cli.py` with
    `_gh_repo_nwo` + raw GraphQL call, split `_gh_fetch` (subprocess
    part moves, reshape stays), move `checks.py` gh calls to
    `utils/github/pull_request.py`.
  - **Commit 3** — `utils/claude_code/` package: move
    `utils/claude_code.py` → `_interactive.py`, move `invoke.py` →
    `_invoke.py`, update importers.
  - **Commit 4** — `utils/shell.py`: extract the shared
    `_run_shell_once(cmd, cwd, env)` helper, wire both runners to it.
    This also delivers PRD-600.3.1 for free.
- **Recommendation**: do-now — status is already `ready` and the
  scope is crisp. The four-commit plan is clean and each commit can
  ship as its own PR if preferred. Land commits 1 and 4 first — they
  deliver the most immediate leverage (git primitives + shell helper
  deduplication). Commits 2 and 3 can follow opportunistically.
  Absorbing PRD-600.3.1 makes this a better carrier for Phase 3
  operational hardening too.

