"""Built-in: ensure_worktree — create or resume a git worktree."""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock
from filelock import Timeout as LockTimeout

from darkfactory.engine import CodeEnv, WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.checks import is_resume_safe
from darkfactory.utils import Timeout
from darkfactory.utils.git import (
    GitErr,
    Ok,
    branch_exists_local,
    branch_exists_remote,
    git_run,
)
from darkfactory.workflow import RunContext

_log = logging.getLogger(__name__)


def _worktree_target(repo_root: Path, branch: str) -> Path:
    """Compute the worktree path under ``.worktrees/``.

    Uses the branch name (with slashes replaced) as the directory name.
    """
    safe_name = branch.replace("/", "-")
    return repo_root / ".worktrees" / safe_name


@builtin("ensure_worktree")
def ensure_worktree(ctx: RunContext) -> None:
    """Create (or resume) a git worktree.

    Reads ``WorktreeState`` from ``ctx.state`` for branch name and base_ref.
    If no ``WorktreeState`` is present, raises an error (use ``name_worktree``
    before ``ensure_worktree``).

    On success, replaces ``CodeEnv`` with updated ``cwd=worktree_path``
    and replaces ``WorktreeState`` with ``worktree_path`` set.

    In live mode, acquires a per-branch advisory file lock at
    ``.worktrees/{branch_safe}.lock`` before any mutation so two concurrent
    runs for the same branch fail fast.
    """
    wt = ctx.state.get(WorktreeState)
    env = ctx.state.get(CodeEnv)
    repo_root = env.repo_root
    branch = wt.branch
    base_ref = wt.base_ref

    worktree_path = _worktree_target(repo_root, branch)

    if _log_dry_run(ctx, f"git worktree add -b {branch} {worktree_path} {base_ref}"):
        # Dry-run produces no side effects, so no lock needed.
        ctx.state.put(CodeEnv(repo_root=repo_root, cwd=worktree_path))
        ctx.state.put(
            WorktreeState(branch=branch, base_ref=base_ref, worktree_path=worktree_path)
        )
        return

    # Acquire the lock BEFORE the resume-check or any mutation.
    safe_name = branch.replace("/", "-")
    lock_path = repo_root / ".worktrees" / f"{safe_name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=0)  # non-blocking
    except LockTimeout:
        raise RuntimeError(
            f"Branch {branch!r} is already being worked on by another process "
            f"(lock held on {lock_path}). If that process died, "
            f"the lock will auto-release when its file handle is reclaimed. "
            f"On a stuck lock, delete {lock_path} manually."
        ) from None

    # Store the lock on the context for the runner to release later.
    ctx._worktree_lock = lock  # type: ignore[attr-defined]

    # ---- existing logic below, now lock-protected ----
    if worktree_path.exists():
        status = is_resume_safe(branch, repo_root)
        if not status.safe:
            lock.release()
            ctx._worktree_lock = None  # type: ignore[attr-defined]
            raise RuntimeError(status.reason)
        ctx.logger.info("resuming existing worktree: %s", worktree_path)
        ctx.state.put(CodeEnv(repo_root=repo_root, cwd=worktree_path))
        ctx.state.put(
            WorktreeState(branch=branch, base_ref=base_ref, worktree_path=worktree_path)
        )
        return

    local_exists = branch_exists_local(repo_root, branch)
    remote_exists = branch_exists_remote(repo_root, branch)
    if local_exists or remote_exists:
        # Release the lock before raising so the error state is clean.
        lock.release()
        ctx._worktree_lock = None  # type: ignore[attr-defined]
        raise RuntimeError(
            f"branch {branch!r} already exists but worktree {worktree_path} is gone. "
            f"Delete the branch manually or run cleanup."
        )

    # git worktree add -b <branch> <path> <base>
    match git_run(
        "worktree",
        "add",
        "-b",
        branch,
        str(worktree_path),
        base_ref,
        cwd=repo_root,
    ):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git worktree add failed (exit {code}):\n{err}")
        case Timeout(timeout=t):
            raise RuntimeError(f"git worktree add timed out after {t}s")

    ctx.state.put(CodeEnv(repo_root=repo_root, cwd=worktree_path))
    ctx.state.put(
        WorktreeState(branch=branch, base_ref=base_ref, worktree_path=worktree_path)
    )
