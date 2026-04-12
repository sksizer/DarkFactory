---
id: PRD-628
title: Refactor git_ops.py to utils/git
kind: task
status: in-progress
priority: medium
effort: m
capability: complex
parent:
depends_on: []
blocks: []
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: '2026-04-11'
tags: []
---

# Refactor git_ops.py to utils/git

## Summary

Consolidate `git_run` and `git_probe` from the orphaned `git_ops.py` into `utils/git/_run.py` (merging the redundant `git_check` into `git_run`), relocate the five helpers in `utils/git/__init__.py` to `utils/git/_operations.py`, and introduce a `utils/git/_types.py` that defines a Result type hierarchy (`Ok[T]`, `GitErr`, `GitTimeout`, `GitResult[T]`) used by all git functions. All five operation helpers migrate to the `_run.py` primitives. Update all 20 affected call sites (19 `git_ops` import sites + `commit_prd_changes.py`) and delete `git_ops.py`. This eliminates two parallel subprocess paths, gives every git call a uniform error shape, and enables structural pattern matching at call sites.

## Motivation

`git_ops.py` is an orphaned module at the package root — it belongs in `utils/git/`, where git helpers already live. More importantly, `utils/git/__init__.py` currently calls `subprocess` directly, duplicating the subprocess wiring already in `git_ops.py`. Two parallel paths to run git commands means error handling diverges silently. Consolidating under a single `_run.py` gateway, with a uniform Result type, gives one place to evolve call conventions (timeouts, logging, retries) and makes error handling at call sites explicit and exhaustive via `match`.

## Requirements

### Functional

1. `utils/git/_types.py` is created and exports: `Ok[T]`, `GitErr`, `GitTimeout`, `GitResult[T]`, `CheckResult`, `ProbeResult`.
   - `Ok[T]` — frozen dataclass with fields `value: T`, `stdout: str = ""`; represents success. `stdout` carries the raw git output for callers that need it (e.g. branch lists, porcelain status); defaults to `""` for check/probe operations where output is irrelevant.
   - `GitErr` — frozen dataclass with fields `returncode: int`, `stdout: str`, `stderr: str`, `cmd: list[str]`; represents a non-zero git exit.
   - `GitTimeout` — frozen dataclass with fields `cmd: list[str]`, `timeout: int`; represents a timed-out probe.
   - `type GitResult[T] = Ok[T] | GitErr`
   - `type CheckResult = GitResult[None]`
   - `type ProbeResult = GitResult[None] | GitTimeout`
   - No `RunResult` alias — `git_run` returns `CheckResult`; callers that need stdout access `ok.stdout` directly.

2. `git_run` and `git_probe` move from `git_ops.py` to `utils/git/_run.py`. `git_check` is removed — it is merged into `git_run`, which now serves both roles:
   - `git_run(*args, cwd) -> CheckResult` — runs git, never raises; returns `Ok(None, stdout=...)` on exit 0, `GitErr` on non-zero. Callers that need stdout destructure `ok.stdout`; callers that only care about success ignore it.
   - `git_probe(*args, cwd, timeout) -> ProbeResult` — same as `git_run` but bounded by a timeout; returns `Ok(None)`, `GitErr`, or `GitTimeout`. Kept separate because its signature and return type differ meaningfully.
   - `git_check` is deleted. All former `git_check` call sites become `git_run`.

3. The five helpers in `utils/git/__init__.py` move to `utils/git/_operations.py` with updated return types:
   - `run_add(paths, cwd) -> CheckResult`
   - `run_commit(message, cwd) -> CheckResult`
   - `diff_quiet(paths, cwd) -> CheckResult`
   - `status_other_dirty(paths, cwd) -> GitResult[list[str]]` — `Ok.value` is the parsed dirty-file list; `Ok.stdout` is the raw porcelain output.
   - `diff_show(paths, cwd) -> None` — unchanged; direct `subprocess.run` call (display function, no result needed).

4. All four non-display helpers in `_operations.py` (`run_add`, `run_commit`, `diff_quiet`, `status_other_dirty`) call `_run.py` primitives — no direct `subprocess` calls.

5. `utils/git/__init__.py` re-exports all public symbols from `_types.py`, `_run.py`, and `_operations.py` so `from darkfactory.utils.git import git_run, Ok, GitErr` (etc.) works.

6. All 19 `from darkfactory.git_ops import ...` sites are updated to `from darkfactory.utils.git import ...` (or `from darkfactory.utils.git._run import ...` for internal callers). All 20 affected call sites (the 19 plus `commit_prd_changes.py`, which already imports from `utils.git`) are updated to use `match` on Result types rather than bare calls, `if bool`, or `try/except CalledProcessError`.

7. `git_ops.py` is deleted.

### Non-Functional

1. `mypy --strict` passes across all modified files.
2. Full test suite passes after the refactor.
3. Peer test file `utils/git/_run_test.py` exists and covers: (a) `git_run` returns `Ok(None, stdout=...)` on exit 0 with stdout populated; (b) `git_run` returns `GitErr` on non-zero exit with `stdout` and `stderr` populated, without raising; (c) `git_probe` returns `GitTimeout` when the command exceeds `timeout`; (d) `git_probe` returns `GitErr` (and does not raise) when the subprocess raises an unexpected exception.
4. Peer test file `utils/git/_operations_test.py` exists and covers: (a) `diff_quiet` returns `Ok(None)` on exit 0 and `GitErr` on non-zero; (b) `run_add` returns `GitErr` on git failure; (c) `run_commit` returns `GitErr` on git failure; (d) `status_other_dirty` returns `Ok([...])` listing files not in the provided paths.

## Technical Approach

**Resulting structure:**

```
utils/git/
  __init__.py       # re-exports from _types.py, _run.py, and _operations.py
  _types.py         # Ok[T], GitErr, GitTimeout, GitResult[T], CheckResult, ProbeResult
  _run.py           # git_run → CheckResult, git_probe → ProbeResult (git_check merged into git_run)
  _operations.py    # diff_quiet, diff_show, status_other_dirty, run_add, run_commit
  branch.py         # imports + call sites: git_ops → ._run, git_check → git_run, try/except → match
  worktree.py       # imports + call sites: git_ops → ._run, git_check → git_run, try/except → match
```

**Result types:**

```python
# _types.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    stdout: str = ""

@dataclass(frozen=True)
class GitErr:
    returncode: int
    stdout: str
    stderr: str
    cmd: list[str]

@dataclass(frozen=True)
class GitTimeout:
    cmd: list[str]
    timeout: int

type GitResult[T] = Ok[T] | GitErr
type CheckResult = GitResult[None]
type ProbeResult = GitResult[None] | GitTimeout
```

**Primitive implementations in `_run.py`:**

`git_run` never raises; `git_probe` never raises and handles timeout. Warning responsibility moves to callers. `git_check` is gone:

```python
def git_run(*args: str, cwd: Path) -> CheckResult:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        return GitErr(result.returncode, result.stdout, result.stderr, ["git", *args])
    return Ok(None, stdout=result.stdout)

def git_probe(*args: str, cwd: Path, timeout: int = 10) -> ProbeResult:
    try:
        result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return GitTimeout(["git", *args], timeout)
    except Exception as exc:
        return GitErr(-1, "", str(exc), ["git", *args])
    if result.returncode != 0:
        return GitErr(result.returncode, result.stdout, result.stderr, ["git", *args])
    return Ok(None, stdout=result.stdout)
```

**Operation implementations in `_operations.py`:**

```python
def run_add(paths: list[str], cwd: Path) -> CheckResult:
    return git_run("add", "--", *paths, cwd=cwd)

def run_commit(message: str, cwd: Path) -> CheckResult:
    return git_run("commit", "-m", message, cwd=cwd)

def diff_quiet(paths: list[str], cwd: Path) -> CheckResult:
    return git_run("diff", "--quiet", "--", *paths, cwd=cwd)

def status_other_dirty(paths: list[str], cwd: Path) -> GitResult[list[str]]:
    match git_run("status", "--porcelain", cwd=cwd):
        case Ok(stdout=raw):
            other: list[str] = [
                line[3:].strip()
                for line in raw.splitlines()
                if line.strip() and line[3:].strip() not in paths
            ]
            return Ok(other, stdout=raw)
        case GitErr() as err:
            return err
```

**Call site patterns:**

Probe (replaces `if git_check(...)`):
```python
match git_run("rev-parse", "--verify", f"refs/heads/{branch}", cwd=root):
    case Ok():
        return True
    case GitErr():
        return False
```

Must-succeed operation (replaces bare `git_run(...)` that raised):
```python
match git_run("worktree", "add", "-b", branch, str(path), base, cwd=root):
    case Ok():
        pass
    case GitErr(returncode=code, stderr=err):
        raise RuntimeError(f"git worktree add failed (exit {code}):\n{err}")
```

Stdout consumer (replaces `result = git_run(...); result.stdout`):
```python
match git_run("branch", "--list", f"prd/{prd_id}-*", cwd=root):
    case Ok(stdout=output):
        return [line.strip().lstrip("* ") for line in output.splitlines() if line.strip()]
    case GitErr():
        return []
```

Network probe with timeout discrimination:
```python
match git_probe("ls-remote", "--exit-code", "origin", ref, cwd=root):
    case Ok():
        return True
    case GitTimeout(timeout=t):
        _log.warning("ls-remote timed out after %ds", t)
        return False
    case GitErr():
        return False
```

**`capture_output` note:** All `_run.py` primitives use `capture_output=True`. The current `run_add`, `run_commit`, and `diff_quiet` call `subprocess.run` without it, so git output previously flowed to the terminal on success. That output is now captured (and available in `GitErr` on failure, which is an improvement). These functions are called exclusively inside the harness where terminal passthrough is not meaningful, so no call sites are affected.

**Import migration:** All 19 `from darkfactory.git_ops import ...` sites change to `from darkfactory.utils.git import ...`. Any former `git_check` imports become `git_run`. `branch.py` and `worktree.py` — which live inside `utils/git/` — import from `._run` directly rather than from the package `__init__.py`, to avoid a fragile intra-package import cycle if `__init__.py` ever imports from those modules.

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/git_ops.py` does not exist.
- [ ] AC-2: `utils/git/_types.py` exports `Ok`, `GitErr`, `GitTimeout`, `GitResult`, `CheckResult`, `ProbeResult`.
- [ ] AC-3: `utils/git/_run.py` exports `git_run → CheckResult` and `git_probe → ProbeResult`. `git_check` does not exist.
- [ ] AC-4: `utils/git/_operations.py` exports `run_add → CheckResult`, `run_commit → CheckResult`, `diff_quiet → CheckResult`, `status_other_dirty → GitResult[list[str]]`, `diff_show → None`.
- [ ] AC-5: `utils/git/__init__.py` re-exports all public symbols from `_types.py`, `_run.py`, and `_operations.py`; `from darkfactory.utils.git import git_run, Ok, GitErr, diff_quiet` (etc.) all work.
- [ ] AC-6: `run_add`, `run_commit`, `diff_quiet`, and `status_other_dirty` in `_operations.py` contain no direct `subprocess` calls.
- [ ] AC-7: Zero occurrences of `from darkfactory.git_ops` in `src/`. (Sibling worktrees under `.worktrees/` are excluded.)
- [ ] AC-8: No file under `utils/git/` imports from `darkfactory.utils.git` (the package `__init__.py`); `branch.py` and `worktree.py` use the relative form `from darkfactory.utils.git._run import ...`.
- [ ] AC-9: `mypy --strict` passes with no new errors.
- [ ] AC-10: `pytest` passes.
- [ ] AC-11: `utils/git/_run_test.py` covers the four behaviors in NF-3: `git_run` `Ok`/`GitErr` with stdout populated on `Ok` and stdout/stderr on `GitErr`, `git_probe` `GitTimeout` on timeout, `git_probe` `GitErr` on unexpected subprocess exception.
- [ ] AC-12: `utils/git/_operations_test.py` covers the four behaviors in NF-4: `diff_quiet` `Ok`/`GitErr`, `run_add` `GitErr` on failure, `run_commit` `GitErr` on failure, `status_other_dirty` `Ok[list]` with correct filtering.

## Open Questions

- RESOLVED: `diff_show` streams git output directly to the terminal (no `capture_output`). Left as a direct `subprocess.run` call — it is a display function, not an operation, and does not participate in the Result type hierarchy.

- RESOLVED: `status_other_dirty` is included in the primitive migration (Req 4). Its current `check=False` pattern was defensive; `git_run` returning `CheckResult` (not raising) handles the non-zero case cleanly, and callers pattern-match on `Ok[list[str]] | GitErr`.

- RESOLVED: Structured error returns — introduced in this PRD as the `_types.py` Result hierarchy. The deferred follow-up is no longer needed.

- RESOLVED: `capture_output` behavior change — all primitives use `capture_output=True`. Success-path terminal output from `run_add`, `run_commit`, and `diff_quiet` is now captured rather than streamed. This is intentional; these functions run inside the harness. Error output is preserved in `GitErr.stderr`.

## References

- `src/darkfactory/git_ops.py` — source module being deleted
- `src/darkfactory/utils/git/__init__.py` — operations being moved to `_operations.py`
- `src/darkfactory/utils/git/branch.py` — internal caller, import needs updating
- `src/darkfactory/utils/git/worktree.py` — internal caller, import needs updating
- `src/darkfactory/builtins/commit_prd_changes.py` — operations caller, call sites need updating for Result types
