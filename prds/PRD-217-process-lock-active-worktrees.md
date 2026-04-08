---
id: "PRD-217"
title: "Process-level lock for active worktrees (cross-platform)"
kind: task
status: review
priority: high
effort: s
capability: moderate
parent: null
depends_on:
  - "[[PRD-215-prd-concurrency-guard]]"
blocks: []
impacts:
  - src/darkfactory/builtins.py
  - src/darkfactory/runner.py
  - src/darkfactory/workflow.py
  - tests/test_builtins.py
  - pyproject.toml
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - concurrency
  - cross-platform
---

# Process-level lock for active worktrees (cross-platform)

## Summary

PRD-215 added a branch-existence guard to `ensure_worktree`, but it only catches the "stale debris" case (branch exists on disk or origin, but no worktree dir). When a second `prd run` targets a PRD whose worktree dir *already exists and is actively being used* by another runner, the current code takes the **resume path** unconditionally — leading to two runners racing on the same files, git state, and PR creation.

Add a real process-level lock via an advisory file lock on a per-PRD sidecar file. Works on macOS, Linux, **and Windows**. Auto-released on process exit (including crashes) so there is no stale-state cleanup burden.

## Motivation

Real scenario (observed 2026-04-08): runner A started `prd run PRD-216` in one terminal. In a second terminal, running `prd run PRD-216` again immediately entered the "resume existing worktree" branch and began executing in parallel with runner A. Both would have raced on file writes, set_status mutations, and the eventual `gh pr create`. Caught manually before damage occurred.

The `status:` field on the PRD cannot be the lock (see PRD-213: the source repo is never modified by `prd run`, so two runners both see `status: ready`). Branch existence cannot be the lock either (see PRD-215: the guard only fires when the worktree is *absent*, not when it's present and in-use). The only reliable signal that "a runner is actively working on this PRD" is a kernel-managed lock held by the runner process for its lifetime.

This PRD also establishes the pattern that **new concurrency/IO code must be cross-platform from the start**. darkfactory doesn't target Windows today, but coupling new code to Unix-only APIs compounds platform debt. Writing the lock cross-platform from day one costs ~20 extra lines and removes a future migration.

## Requirements

1. Two concurrent `prd run <PRD>` invocations against the same PRD → the second errors out with a clear message within seconds, without touching any file, worktree, branch, or git state.
2. The lock is acquired as the **first real side-effect** of `ensure_worktree`, before the resume-check and before any branch/directory mutation.
3. The lock auto-releases on process exit (normal exit, uncaught exception, `SIGKILL`, power loss). No PID files, no stale-state cleanup code.
4. The runner's task loop explicitly releases the lock when the run completes (belt-and-suspenders — correctness relies on kernel cleanup, tidiness relies on explicit release).
5. Implementation works on **macOS, Linux, and Windows**. CI runs the concurrency test on all three.
6. Dry-run mode does not acquire a lock (nothing to protect — no side effects occur).
7. Resume after a legitimately-interrupted prior run (same worktree dir present, no other runner holding the lock) works exactly as today.
8. Lock files live alongside the worktree dirs at `.worktrees/{prd_id}.lock`. They are tracked by `.gitignore` (whole `.worktrees/` already is).

## Technical Approach

### Library choice: `filelock`

Use the third-party [`filelock`](https://pypi.org/project/filelock/) package (~30M downloads/month, permissively licensed, maintained, minimal transitive deps). It provides a single uniform API that dispatches to `fcntl.flock` on Unix and `msvcrt.locking` / `LockFileEx` on Windows.

**Rejected alternatives:**
- **Raw `fcntl.flock`** — Unix-only. Rejected per user guidance to establish cross-platform patterns from the start.
- **Platform-split with `sys.platform == "win32"` branch** — zero-dep, but ~30 lines of platform code plus per-platform test matrices. `filelock` already does this correctly and we inherit their testing.
- **`portalocker`** — also cross-platform, similar footprint, slightly less popular. No strong reason to prefer it over `filelock`.

### Dependency addition

`pyproject.toml`:

```toml
dependencies = [
    "pyyaml>=6.0",
    "filelock>=3.13",
]
```

### ExecutionContext gains a lock handle

`src/darkfactory/workflow.py`:

```python
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from filelock import FileLock

@dataclass
class ExecutionContext:
    ...
    # Advisory process-level lock held by ensure_worktree for the
    # lifetime of this run. Managed by builtins + runner; tests should
    # not touch it directly.
    _worktree_lock: "FileLock | None" = field(default=None, repr=False)
```

### `ensure_worktree` acquires the lock

`src/darkfactory/builtins.py`:

```python
from filelock import FileLock, Timeout

@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None:
    worktree_path = _worktree_target(ctx)
    branch = ctx.branch_name

    if ctx.dry_run:
        # Dry-run does nothing destructive, so no lock needed.
        ctx.logger.info(
            "[dry-run] git worktree add -b %s %s %s",
            branch, worktree_path, ctx.base_ref,
        )
        return

    # Acquire the lock BEFORE the resume-check or any mutation.
    # The lock file lives at .worktrees/PRD-X.lock and is per-PRD.
    lock_path = ctx.repo_root / ".worktrees" / f"{ctx.prd.id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=0)  # non-blocking
    except Timeout:
        raise RuntimeError(
            f"{ctx.prd.id} is already being worked on by another `prd run` "
            f"process (lock held on {lock_path}). If that process died, "
            f"the lock will auto-release when its file handle is reclaimed. "
            f"On a stuck lock, delete {lock_path} manually."
        ) from None

    ctx._worktree_lock = lock

    # ---- existing logic below, now lock-protected ----
    if worktree_path.exists():
        ctx.logger.info("resuming existing worktree: %s", worktree_path)
        ctx.worktree_path = worktree_path
        ctx.cwd = worktree_path
        return

    if _branch_exists_local(ctx.repo_root, branch) or _branch_exists_remote(ctx.repo_root, branch):
        # Release the lock before raising so the error state is clean.
        lock.release()
        ctx._worktree_lock = None
        raise RuntimeError(
            f"branch {branch!r} already exists but worktree {worktree_path} is gone. "
            f"Run `prd cleanup {ctx.prd.id}` to release it."
        )

    # ... existing git worktree add call ...
```

### Runner releases on exit

`src/darkfactory/runner.py`:

```python
def run_tasks(ctx: ExecutionContext) -> TaskOutcome:
    try:
        # ... existing task loop ...
        return outcome
    finally:
        _release_worktree_lock(ctx)


def _release_worktree_lock(ctx: ExecutionContext) -> None:
    """Release the advisory lock acquired by ensure_worktree, if any.

    Safe to call multiple times and on contexts that never acquired a
    lock (e.g. dry-run paths).
    """
    lock = ctx._worktree_lock
    if lock is None:
        return
    try:
        lock.release()
    except Exception as exc:  # noqa: BLE001
        ctx.logger.warning("failed to release worktree lock: %s", exc)
    finally:
        ctx._worktree_lock = None
```

Even if the runner fails to reach the `finally`, `filelock`'s context lifecycle ensures the underlying fd / handle is released when the Python process exits — which is ultimately enforced by the kernel on Unix and by Windows on process termination.

### Dry-run bypass

Dry-run produces no side effects, so it skips lock acquisition entirely. This means `prd plan PRD-X` is safe to run from multiple terminals simultaneously (a common use case) without artificial contention.

### Test matrix

Tests live in `tests/test_builtins.py` under a new `# ---------- process lock ----------` section.

1. **`test_ensure_worktree_acquires_lock`** — after calling `ensure_worktree`, assert `ctx._worktree_lock is not None` and the lock file exists.
2. **`test_ensure_worktree_refuses_when_locked`** — open a `FileLock` on the expected path in the test, hold it, call `ensure_worktree`, assert `RuntimeError` with "already being worked on".
3. **`test_ensure_worktree_dry_run_no_lock`** — dry-run path doesn't create or acquire the lock.
4. **`test_ensure_worktree_releases_on_branch_guard_raise`** — when the branch-exists guard (PRD-215) fires, the lock must be released so a subsequent retry isn't permanently locked out.
5. **`test_runner_releases_lock_on_success`** — drive a full workflow through `run_tasks` with a stub workflow, assert lock is released on the context at the end.
6. **`test_runner_releases_lock_on_exception`** — workflow task raises mid-run, lock is still released.
7. **`test_lock_auto_releases_on_subprocess_exit`** — launch a child `python -c "..."` that acquires the lock and exits. From the test process, verify we can acquire it afterward. This is the cross-process correctness check; it exercises the kernel's cleanup behavior.

### CI matrix

Update `.github/workflows/ci.yml` (when it exists; see PRD-530) to run the suite on `ubuntu-latest`, `macos-latest`, and `windows-latest`. The concurrency tests above must all pass on each.

Until CI is set up, manual verification on macOS is the baseline. Windows verification can be deferred to CI introduction; `filelock`'s own test suite covers the Windows path at the library level.

## Acceptance Criteria

- [ ] AC-1: Two concurrent `uv run prd run PRD-X --execute` against the same PRD → second process errors within ~1 second with a clear message naming the lock file.
- [ ] AC-2: `prd plan PRD-X` (dry-run) runs in multiple terminals simultaneously without contention.
- [ ] AC-3: A crashing runner (SIGKILL of the python process while `ensure_worktree` is holding the lock) leaves no stale lock — the next `prd run` succeeds immediately.
- [ ] AC-4: A runner whose branch-exists guard (PRD-215) fires releases the lock before raising, so a follow-up `prd cleanup` and retry works.
- [ ] AC-5: All 7 tests from the test matrix above pass on macOS.
- [ ] AC-6: `filelock` is listed as a runtime dependency in `pyproject.toml` and `uv.lock` reflects the resolution.
- [ ] AC-7: The lock file path is `.worktrees/{prd_id}.lock`, already ignored by `.gitignore`'s `.worktrees/` entry.
- [ ] AC-8: `ExecutionContext` exposes `_worktree_lock` (underscore-prefixed, not in `repr`) so tests can inspect state without it being part of the public API.
- [ ] AC-9: README notes that the harness's `prd run` uses advisory file locking and works on macOS, Linux, and Windows; read-only subcommands (`prd status`, `prd plan`, `prd validate`) do not acquire locks.

## Open Questions

- [ ] Should the lock be scoped per-PRD (`PRD-216.lock`) or per-worktree-dir (`.worktrees/.lock`)? Per-PRD is finer-grained and allows running different PRDs in parallel — which is the desired behavior once PRD-220 graph execution lands. Recommendation: per-PRD. (AC-1/AC-2 above assume this.)
- [ ] Should we log lock acquisition at INFO or DEBUG? Probably DEBUG — it's noise on the happy path, and the contention case raises a clear error so the user sees that regardless. Recommendation: DEBUG.
- [ ] Should `prd cleanup` (future) remove the `.lock` file when it removes the worktree? Yes — once the worktree is gone the lock is meaningless. Track as part of PRD-cleanup's scope, not here.

## References

- [[PRD-213-set-status-wrong-repo]] — establishes "source repo untouched" invariant; the reason `status:` can't serve as the lock
- [[PRD-215-prd-concurrency-guard]] — covers the complementary "stale debris" case; this PRD is the companion that covers "active contention"
- [[PRD-220-graph-execution]] — will exercise the per-PRD lock granularity once parallel sibling execution is implemented
- [filelock on PyPI](https://pypi.org/project/filelock/)
- [Python fcntl.flock docs](https://docs.python.org/3/library/fcntl.html#fcntl.flock)
- [Python msvcrt.locking docs](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking)
