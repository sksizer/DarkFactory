"""Built-in: fast_forward_branch — sync local branch with its origin remote.

Fast-forwards the worktree's local branch to match ``origin/<branch>``.
Solves the "push rejected" problem where a previous rework cycle or
external push has advanced the remote branch beyond the local worktree.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)

_DEFAULT_FETCH_TIMEOUT = 30


def _fetch_origin_branch(cwd: Path, branch: str, timeout: int) -> bool:
    """Fetch ``origin/<branch>`` with a timeout.

    Returns ``True`` if the fetch succeeded, ``False`` if the remote ref
    does not exist (treated as already-up-to-date — nothing to sync).

    Raises :class:`RuntimeError` on timeout or any other fetch failure.
    """
    try:
        result = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"git fetch origin {branch} timed out after {timeout}s — "
            "check network connectivity or increase fetch_timeout"
        )

    if result.returncode == 0:
        return True

    # "couldn't find remote ref" means the branch hasn't been pushed yet.
    combined = result.stdout + result.stderr
    if "couldn't find remote ref" in combined:
        return False

    raise RuntimeError(
        f"git fetch origin {branch} failed (exit {result.returncode}):\n{result.stderr}"
    )


def _check_divergence(cwd: Path, branch: str) -> tuple[int, int] | None:
    """Return ``(ahead, behind)`` counts between HEAD and ``origin/<branch>``.

    Returns ``None`` if ``origin/<branch>`` does not exist locally (e.g.
    because a preceding fetch treated the remote as missing and returned
    early).  In that case the caller should treat the branch as up-to-date.
    """
    # Verify the remote ref is present locally before running rev-list.
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch}"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return None

    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    parts = result.stdout.strip().split()
    return int(parts[0]), int(parts[1])


def _get_head_sha(cwd: Path) -> str:
    """Return the short SHA of HEAD."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@builtin("fast_forward_branch")
def fast_forward_branch(
    ctx: ExecutionContext,
    *,
    fetch_timeout: int = _DEFAULT_FETCH_TIMEOUT,
) -> None:
    """Fast-forward local branch to match ``origin/<branch>``.

    Steps:

    1. ``git fetch origin <branch>`` (with timeout).  Missing remote ref
       is treated as already-up-to-date.
    2. ``git rev-list --left-right --count HEAD...origin/<branch>`` to
       measure divergence.
    3. Act on the result:

       - ``0 0`` → no-op, emit ``result="up_to_date"``.
       - ``0 N`` → fast-forward via ``git merge --ff-only``, emit
         ``result="fast_forward"`` with ``from_sha``/``to_sha``/``commits``.
       - ``M 0`` → fail loudly (unpushed local commits).
       - ``M N`` → fail loudly (genuine divergence).

    Raises :class:`RuntimeError` on divergence, fetch failure, or timeout.
    """
    branch = ctx.branch_name
    cwd = ctx.cwd

    remote_found = _fetch_origin_branch(cwd, branch, fetch_timeout)

    if not remote_found:
        _log.info(
            "fast_forward_branch: remote ref origin/%s not found — up-to-date by definition",
            branch,
        )
        emit_builtin_effect(ctx, "fast_forward_branch", "sync", result="up_to_date")
        return

    divergence = _check_divergence(cwd, branch)

    if divergence is None:
        # Ref not in local refstore despite successful fetch — treat as up-to-date.
        emit_builtin_effect(ctx, "fast_forward_branch", "sync", result="up_to_date")
        return

    ahead, behind = divergence

    if ahead == 0 and behind == 0:
        emit_builtin_effect(ctx, "fast_forward_branch", "sync", result="up_to_date")
        return

    if ahead > 0 and behind == 0:
        raise RuntimeError(
            f"local branch {branch} is {ahead} commit(s) ahead of origin — "
            "this usually means a previous push failed; investigate and resolve manually."
        )

    if ahead > 0 and behind > 0:
        raise RuntimeError(
            f"local branch {branch} has diverged from origin "
            f"({ahead} ahead, {behind} behind) — investigate and resolve manually."
        )

    # ahead == 0, behind > 0: fast-forward
    old_sha = _get_head_sha(cwd)
    git_run("merge", "--ff-only", f"origin/{branch}", cwd=cwd)
    new_sha = _get_head_sha(cwd)

    _log.info(
        "fast_forward_branch: %s fast-forwarded %s → %s (%d commit(s))",
        branch,
        old_sha[:8],
        new_sha[:8],
        behind,
    )
    emit_builtin_effect(
        ctx,
        "fast_forward_branch",
        "sync",
        result="fast_forward",
        from_sha=old_sha,
        to_sha=new_sha,
        commits=behind,
    )
