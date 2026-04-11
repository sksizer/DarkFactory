"""Built-in: ensure_worktree — create or resume a git worktree for a PRD."""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.checks import is_resume_safe
from darkfactory.utils.git import git_check, git_probe, git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


def _worktree_target(ctx: ExecutionContext) -> Path:
    """Compute the worktree path for this PRD under ``.worktrees/``.

    Separated out so tests can assert the path without a whole
    subprocess invocation.
    """
    return ctx.repo_root / ".worktrees" / f"{ctx.prd.id}-{ctx.prd.slug}"


def _branch_exists_local(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists in the local repo's refs."""
    return git_check(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        cwd=repo_root,
    )


def _branch_exists_remote(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists on origin.

    Best-effort: returns False (and logs a warning) on timeout or any
    subprocess error so the caller can fall back to the local check.
    """
    return git_probe(
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{branch}",
        cwd=repo_root,
    )


@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None:
    """Create (or resume) a git worktree for this PRD.

    Target path: ``{repo_root}/.worktrees/{prd_id}-{slug}``. Branch:
    ``prd/{prd_id}-{slug}`` created from ``ctx.base_ref``. If the
    worktree already exists (previous run resumed), reuses it without
    re-creating. Sets ``ctx.worktree_path`` and ``ctx.cwd`` on success.

    In live mode, acquires a per-PRD advisory file lock at
    ``.worktrees/{prd_id}.lock`` before any mutation so two concurrent
    ``prd run`` invocations for the same PRD fail fast with a clear
    message instead of racing. The lock is auto-released by the kernel
    when the process exits; the runner also releases it explicitly at the
    end of the run (see ``_release_worktree_lock``).
    """
    worktree_path = _worktree_target(ctx)
    branch = ctx.branch_name

    if _log_dry_run(
        ctx, f"git worktree add -b {branch} {worktree_path} {ctx.base_ref}"
    ):
        # Dry-run produces no side effects, so no lock needed.
        ctx.worktree_path = worktree_path
        ctx.cwd = worktree_path
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
        status = is_resume_safe(branch, ctx.repo_root)
        if not status.safe:
            lock.release()
            ctx._worktree_lock = None
            raise RuntimeError(status.reason)
        ctx.logger.info("resuming existing worktree: %s", worktree_path)
        ctx.worktree_path = worktree_path
        ctx.cwd = worktree_path
        return

    local_exists = _branch_exists_local(ctx.repo_root, branch)
    remote_exists = _branch_exists_remote(ctx.repo_root, branch)
    if local_exists or remote_exists:
        # Release the lock before raising so the error state is clean.
        lock.release()
        ctx._worktree_lock = None
        raise RuntimeError(
            f"branch {branch!r} already exists but worktree {worktree_path} is gone. "
            f"Run `prd cleanup {ctx.prd.id}` to release it."
        )

    # git worktree add -b <branch> <path> <base>
    # Run from the repo root, not from ctx.cwd (which may not be a git dir yet).
    git_run(
        "worktree",
        "add",
        "-b",
        branch,
        str(worktree_path),
        ctx.base_ref,
        cwd=ctx.repo_root,
    )

    ctx.worktree_path = worktree_path
    ctx.cwd = worktree_path
