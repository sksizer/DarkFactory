---
id: PRD-621
title: Refactor common functionality in regards to external systems, services, commands to util modules
kind: task
status: ready
priority: medium
effort: m
capability: complex
parent:
depends_on:
  - "[[PRD-628-refactor-gitopspy-to-utilsgit]]"
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

# Refactor external system utilities (GitHub, Claude Code, shell)

## Summary

Consolidate scattered `gh` CLI interactions into `utils/github/` with a Result type hierarchy parallel to PRD-628's git design, move Claude Code subprocess logic into `utils/claude_code/`, and extract the duplicated shell runner into `utils/shell.py`. Promote `Ok[T]` from `utils/git/_types.py` to a shared `utils/_result.py` so both `utils/git/` and `utils/github/` use the same success type. The `utils/git/` consolidation is handled by PRD-628; this PRD covers the remaining three packages.

## Motivation

GitHub CLI calls are scattered across 4 modules (`pr_comments.py`, `checks.py`, `builtins/create_pr.py`, `utils/github/__init__.py`) with 9 independent `subprocess.run(["gh", ...])` invocations, each with its own error handling (some raise, some return defaults, some log-and-skip). Claude Code invocation is split between two unrelated modules (`invoke.py` at the package root and `utils/claude_code.py`). The shell runner is duplicated verbatim across `runner.py` and `system_runner.py`.

Consolidating behind typed primitives with Result returns — parallel to what PRD-628 does for git — gives consistent error handling, makes `gh` failures explicit at call sites via `match`, and makes it easy to find all external-system code in the tree.

## Requirements

### Functional

**Ok[T] promotion:**

1. `Ok[T]` moves from `utils/git/_types.py` to `utils/_result.py`. `utils/git/_types.py` re-imports it from there so PRD-628 callers are unaffected. `Ok[T]` is not git-specific — it is a generic success wrapper reused across `utils/git/` and `utils/github/`.

**GitHub CLI — `utils/github/`:**

2. `utils/github/_types.py` is created and exports:
   - `GhErr` — frozen dataclass with fields `returncode: int`, `stdout: str`, `stderr: str`, `cmd: list[str]`. Same shape as `GitErr` but a distinct type for type-level discrimination.
   - `type GhResult[T] = Ok[T] | GhErr`
   - `type GhCheckResult = GhResult[None]`

3. `utils/github/_cli.py` is created with two primitives:
   - `gh_run(*args, cwd) -> GhCheckResult` — runs `gh` subprocess, never raises. Returns `Ok(None, stdout=...)` on exit 0, `GhErr` on non-zero. Parallel to `git_run`.
   - `gh_json(*args, cwd) -> GhResult[Any]` — runs `gh` subprocess, parses stdout as JSON on success. Returns `Ok(parsed, stdout=raw)` or `GhErr`.

4. `utils/github/pull_request.py` is created. Functions that move here:
   - `get_pr_state(branch, repo_root) -> GhResult[str]` — from `checks.py:_get_pr_state`. Returns `Ok("MERGED")`, `Ok("OPEN")`, etc., or `GhErr`. Callers distinguish "gh failed" from "no PR" (currently conflated into `"UNKNOWN"`).
   - `fetch_all_pr_states(repo_root) -> GhResult[dict[str, str]]` — from `checks.py:_fetch_all_pr_states`. Branch-to-state mapping with MERGED>CLOSED>OPEN priority.
   - `get_resume_pr_state(branch, repo_root) -> GhResult[list[dict[str, Any]]]` — extracted from `checks.py:is_resume_safe`. Returns the raw PR list (`state`, `mergedAt` fields) so `is_resume_safe` can interpret it. `is_resume_safe` stays in `checks.py` as business logic.
   - `create_pr(base, title, body_path, cwd) -> GhResult[str]` — extracted from `builtins/create_pr.py`. Returns the PR URL on success. The builtin keeps its orchestration (title/body construction, `ctx.pr_url` assignment) and calls this function for the subprocess.
   - `list_open_prs(repo_root, limit) -> GhResult[list[PrInfo]]` — from `utils/github/__init__.py`. Same semantics, Result return type.
   - `close_pr(pr_number, repo_root, comment) -> GhCheckResult` — from `utils/github/__init__.py`. Same semantics, Result return type.
   - `PrInfo` dataclass stays (moved from `utils/github/__init__.py`).

5. `utils/github/_comments.py` is created with the raw `gh` call extracted from `pr_comments.py`:
   - `graphql_fetch(query, variables, cwd) -> GhResult[dict[str, Any]]` — the raw `gh api graphql` subprocess call from `_gh_fetch()`. Response reshaping stays in `pr_comments.py`.
   - `post_reply(endpoint, body, cwd) -> GhCheckResult` — the raw `gh api POST` subprocess call from `post_comment_replies()`. Orchestration stays in `pr_comments.py`.
   - `repo_nwo(cwd) -> GhResult[tuple[str, str]]` — from `pr_comments.py:_gh_repo_nwo()`. Returns `(owner, name)`.

6. `pr_comments.py` business logic stays in place. It imports from `utils/github/_comments.py` for subprocess calls. Specific changes:
   - `_gh_fetch()` calls `graphql_fetch()` then reshapes the response.
   - `post_comment_replies()` calls `post_reply()` for each reply.
   - `_gh_repo_nwo()` is deleted; replaced by `from darkfactory.utils.github import repo_nwo`.
   - `_resolve_commit_timestamp()` moves to `utils/git/_operations.py` (clean `git log` wrapper using `git_run`; returns `GitResult[str]`). PRD-628 creates `_operations.py` — this adds one function.

7. `checks.py` keeps `is_resume_safe()`, `SubprocessGitState`, `StaleWorktree`, `ResumeStatus`, and `find_stale_worktrees()`. The `gh` subprocess calls are replaced with imports from `utils/github/pull_request.py`. The `git` subprocess calls in `is_resume_safe` are replaced with `git_run` from `utils/git`.

**Claude Code — `utils/claude_code/`:**

8. `utils/claude_code.py` (flat file) becomes `utils/claude_code/_interactive.py`. `spawn_claude()` and `EffortLevel` move unchanged — no Result type (interactive terminal function, same reasoning as `diff_show`).

9. `invoke.py` (package root) becomes `utils/claude_code/_invoke.py`. `invoke_claude()`, `InvokeResult`, and `capability_to_model()` move unchanged — `InvokeResult` already serves as a result type for the streaming/sentinel use case. No signature changes.

10. `utils/claude_code/__init__.py` re-exports: `spawn_claude`, `EffortLevel`, `invoke_claude`, `InvokeResult`, `capability_to_model`.

**Shell runner — `utils/shell.py`:**

11. `utils/shell.py` is created with `run_shell(cmd, cwd, env) -> subprocess.CompletedProcess[str]` extracted from the identical `_run_shell_once` in `runner.py` (line 580) and `system_runner.py` (line 356). Accepts `cwd: Path` directly instead of a context object. Both callers updated to import from `utils.shell` and pass `ctx.cwd`.

**Cleanup:**

12. Old modules deleted: `invoke.py` (package root), `utils/claude_code.py` (flat file). `utils/github/__init__.py` becomes a re-export hub (existing `list_open_prs`, `close_pr`, `PrInfo` move to `pull_request.py`). No shims at old paths.

13. All import sites updated. Call sites for GitHub functions updated to `match` on Result types.

### Non-Functional

1. `mypy --strict` passes across all modified files.
2. Full test suite passes (import path updates in test files as needed).
3. No new runtime dependencies.
4. Peer test file `utils/github/_cli_test.py` exists and covers: (a) `gh_run` returns `Ok` on exit 0 with stdout populated; (b) `gh_run` returns `GhErr` on non-zero exit without raising; (c) `gh_json` returns `Ok(parsed_data)` on valid JSON stdout; (d) `gh_json` returns `GhErr` on non-zero exit.

## Technical Approach

**Resulting structure:**

```
utils/
  _result.py              # Ok[T] — shared success type (promoted from utils/git/_types.py)
  shell.py                # run_shell(cmd, cwd, env)
  git/
    _types.py             # imports Ok from .._result; GitErr, GitTimeout, CheckResult, ProbeResult
    _run.py               # git_run, git_probe (from PRD-628)
    _operations.py        # diff_quiet, run_add, etc. + _resolve_commit_timestamp (from PRD-628 + this PRD)
    branch.py             # (from PRD-628)
    worktree.py           # (from PRD-628)
    __init__.py           # re-exports
  github/
    _types.py             # GhErr, GhResult[T], GhCheckResult
    _cli.py               # gh_run, gh_json (primitives)
    _comments.py          # graphql_fetch, post_reply, repo_nwo
    pull_request.py       # get_pr_state, fetch_all_pr_states, create_pr, list_open_prs, close_pr, PrInfo
    __init__.py           # re-exports
  claude_code/
    _interactive.py       # spawn_claude, EffortLevel (from utils/claude_code.py)
    _invoke.py            # invoke_claude, InvokeResult, capability_to_model (from invoke.py)
    __init__.py           # re-exports
```

**`Ok[T]` promotion — `utils/_result.py`:**

```python
# utils/_result.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    stdout: str = ""
```

`utils/git/_types.py` changes its `Ok` definition to `from darkfactory.utils._result import Ok`. All existing callers are unaffected — they import `Ok` from `utils.git` which re-exports it.

**GitHub Result types — `utils/github/_types.py`:**

```python
# utils/github/_types.py
from __future__ import annotations
from dataclasses import dataclass
from darkfactory.utils._result import Ok

@dataclass(frozen=True)
class GhErr:
    returncode: int
    stdout: str
    stderr: str
    cmd: list[str]

type GhResult[T] = Ok[T] | GhErr
type GhCheckResult = GhResult[None]
```

**GitHub primitives — `utils/github/_cli.py`:**

```python
def gh_run(*args: str, cwd: Path) -> GhCheckResult:
    result = subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        return GhErr(result.returncode, result.stdout, result.stderr, ["gh", *args])
    return Ok(None, stdout=result.stdout)

def gh_json(*args: str, cwd: Path) -> GhResult[Any]:
    match gh_run(*args, cwd=cwd):
        case Ok(stdout=raw):
            return Ok(json.loads(raw), stdout=raw)
        case GhErr() as err:
            return err
```

**GitHub call site patterns:**

PR state query (replaces `_get_pr_state` with try/except and "UNKNOWN" fallback):
```python
match get_pr_state(branch, repo_root):
    case Ok(value=state):
        pr_states[branch] = state
    case GhErr():
        pr_states[branch] = "UNKNOWN"
```

PR creation (replaces bare `subprocess.run(["gh", "pr", "create", ...], check=True)`):
```python
match create_pr(ctx.base_ref, title, body_path, ctx.cwd):
    case Ok(value=url):
        ctx.pr_url = url
    case GhErr(returncode=code, stderr=err):
        raise RuntimeError(f"gh pr create failed (exit {code}):\n{err}")
```

**Import site counts:**

| Old location | Importers | What moves |
|---|---|---|
| `pr_comments.py` (subprocess bits) | 11 | `_gh_repo_nwo`, `_gh_fetch` raw call, `post_comment_replies` raw call, `_resolve_commit_timestamp` |
| `checks.py` (gh calls) | 6 | `_get_pr_state`, `_fetch_all_pr_states`, `is_resume_safe` gh/git calls |
| `builtins/create_pr.py` (gh call) | — | `gh pr create` subprocess extracted |
| `utils/github/__init__.py` | 1 | `list_open_prs`, `close_pr`, `PrInfo` → `pull_request.py` |
| `invoke.py` | 3 | Entire module → `utils/claude_code/_invoke.py` |
| `utils/claude_code.py` | 3 | Entire module → `utils/claude_code/_interactive.py` |
| `runner.py` / `system_runner.py` | — | `_run_shell_once` extracted, callers updated |

**Migration order — 4 atomic commits:**

**Commit 1 — `Ok[T]` promotion + `_resolve_commit_timestamp`:**
- Create `utils/_result.py` with `Ok[T]`.
- Update `utils/git/_types.py` to import `Ok` from `utils._result`.
- Move `_resolve_commit_timestamp()` from `pr_comments.py` to `utils/git/_operations.py`, using `git_run`.
- Verify: all existing git Result call sites still work.

**Commit 2 — `utils/github/`:**
- Create `_types.py`, `_cli.py`, `_comments.py`, `pull_request.py`.
- Move functions per Req 4–7. Update `checks.py`, `pr_comments.py`, `builtins/create_pr.py`, `utils/github/__init__.py`.
- Delete old `gh` subprocess calls from source files.
- Verify: `grep -r 'subprocess.run.*\["gh"' src/` returns only `utils/github/`.

**Commit 3 — `utils/claude_code/`:**
- `utils/claude_code.py` → `utils/claude_code/_interactive.py`.
- `invoke.py` → `utils/claude_code/_invoke.py`.
- Create `utils/claude_code/__init__.py` with re-exports.
- Update 6 import sites. Delete old modules.
- Verify: `grep -r 'from darkfactory.invoke import' src/` and `grep -r 'from darkfactory.utils.claude_code import' src/` (flat file form) return zero matches.

**Commit 4 — `utils/shell.py`:**
- Extract `run_shell(cmd, cwd, env)` to `utils/shell.py`.
- Update `runner.py` and `system_runner.py` to import from `utils.shell`.
- Delete `_run_shell_once` from both runners.

## Acceptance Criteria

- [ ] AC-1: `utils/_result.py` exports `Ok[T]`; `utils/git/_types.py` imports `Ok` from there (not locally defined).
- [ ] AC-2: `utils/github/_types.py` exports `GhErr`, `GhResult`, `GhCheckResult`.
- [ ] AC-3: `utils/github/_cli.py` exports `gh_run → GhCheckResult` and `gh_json → GhResult[Any]`.
- [ ] AC-4: `utils/github/pull_request.py` exports `get_pr_state`, `fetch_all_pr_states`, `get_resume_pr_state`, `create_pr`, `list_open_prs`, `close_pr`, `PrInfo` — all returning `GhResult`/`GhCheckResult` types.
- [ ] AC-5: `utils/github/_comments.py` exports `graphql_fetch`, `post_reply`, `repo_nwo` — all returning `GhResult`/`GhCheckResult` types.
- [ ] AC-6: Zero occurrences of `subprocess.run(["gh"` outside `utils/github/` in `src/`. (Tests excluded.)
- [ ] AC-7: `pr_comments.py` retains business logic (filtering, threading, reply parsing) but contains zero direct `gh` or `git` subprocess calls.
- [ ] AC-8: `checks.py:is_resume_safe()` contains zero direct `gh` or `git` subprocess calls — it calls through `utils/github/` and `utils/git/`.
- [ ] AC-9: `_resolve_commit_timestamp()` lives in `utils/git/_operations.py` and uses `git_run`, returning `GitResult[str]`.
- [ ] AC-10: `utils/claude_code/` package exists; `invoke.py` (root) and `utils/claude_code.py` (flat file) are deleted.
- [ ] AC-11: Zero occurrences of `from darkfactory.invoke import` in `src/`.
- [ ] AC-12: `utils/shell.py` exports `run_shell`; no `_run_shell_once` function exists in `runner.py` or `system_runner.py`.
- [ ] AC-13: `mypy --strict` passes.
- [ ] AC-14: `pytest` passes.
- [ ] AC-15: `utils/github/_cli_test.py` covers the four behaviors in NF-4.

## Open Questions

- RESOLVED: Shims at old import paths? — No, update all call sites directly.

- RESOLVED: `SubprocessGitState` in `checks.py`? — Stays in `checks.py`. It only makes `git ls-remote` calls (not `gh`), is tightly coupled to the checks domain, and has no reuse elsewhere.

- RESOLVED: `utils/git/` structure? — Handled entirely by PRD-628. This PRD only adds `_resolve_commit_timestamp` to the existing `_operations.py`.

- RESOLVED: Does AC-6 ("no `gh` calls outside `utils/github/`") require changes to tests? — No. Tests mock at the function boundary, not at subprocess level.

- RESOLVED: Result types for `invoke_claude` / `spawn_claude`? — No. `InvokeResult` already serves as a result type for the streaming/sentinel use case. `spawn_claude` is an interactive terminal function (same reasoning as `diff_show` in PRD-628).

- RESOLVED: Result types for `run_shell`? — No. It is an internal utility for two runners that process `CompletedProcess` directly. Result types would add indirection without improving those call sites.

- RESOLVED: `is_resume_safe` has interleaved `gh` and `git` subprocess calls. The `gh pr list` call is extracted to `get_resume_pr_state()` in `utils/github/pull_request.py`. The `git rev-parse` / `git rev-list` calls are updated to use `git_run` from `utils/git/`. `is_resume_safe` stays in `checks.py` as business logic.

## References

- `src/darkfactory/pr_comments.py` — GitHub comment logic (~510 lines, 3 `gh` subprocess calls)
- `src/darkfactory/checks.py` — PR state checks (~350 lines, 3 `gh` calls + 3 `git` calls in `is_resume_safe`)
- `src/darkfactory/builtins/create_pr.py` — PR creation builtin (1 `gh` call)
- `src/darkfactory/utils/github/__init__.py` — existing `list_open_prs`, `close_pr` (2 `gh` calls)
- `src/darkfactory/invoke.py` — Claude Code invocation (~688 lines, 1 Popen call)
- `src/darkfactory/utils/claude_code.py` — `spawn_claude` (~38 lines, 1 subprocess call)
- `src/darkfactory/runner.py:580-599` — shell runner (duplicated)
- `src/darkfactory/system_runner.py:356-373` — shell runner (duplicate)

  
