"""Built-in: rebase_onto_main — rebase worktree branch onto origin/main.

Rebases the worktree's branch onto ``origin/main`` so the agent always
works against current mainline code.  On conflict, aborts the rebase
cleanly and fails loudly with the list of conflicting files.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.event_log import emit_builtin_effect
from darkfactory.git_ops import git_check
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)

_DEFAULT_FETCH_TIMEOUT = 30


def _fetch_origin_main(cwd: Path, timeout: int) -> None:
    """Fetch ``origin/main`` with a timeout.

    Raises :class:`RuntimeError` on timeout or non-zero exit.
    """
    try:
        result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"git fetch origin main timed out after {timeout}s — "
            "check network connectivity or increase fetch_timeout"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"git fetch origin main failed (exit {result.returncode}):\n{result.stderr}"
        )


def _get_sha(cwd: Path, ref: str) -> str:
    """Return the full SHA for ``ref``."""
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_conflicting_files(cwd: Path) -> list[str]:
    """Return a list of files with unresolved merge conflicts."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()


@builtin("rebase_onto_main")
def rebase_onto_main(
    ctx: ExecutionContext,
    *,
    fetch_timeout: int = _DEFAULT_FETCH_TIMEOUT,
) -> None:
    """Rebase the worktree branch onto ``origin/main``.

    Steps:

    1. ``git fetch origin main`` (with timeout).
    2. ``git merge-base --is-ancestor origin/main HEAD`` to check if
       already up-to-date.  If yes → emit ``result="up_to_date"`` and return.
    3. ``git rebase origin/main``.

       - On success → emit ``result="rebased"`` with ``from_sha``/``to_sha``/
         ``onto_sha``.
       - On conflict → ``git rebase --abort`` to restore clean state, then
         raise with the list of conflicting files.

    Raises :class:`RuntimeError` on fetch failure, timeout, or rebase conflict.
    """
    cwd = ctx.cwd

    _fetch_origin_main(cwd, fetch_timeout)

    already_up_to_date = git_check(
        "merge-base", "--is-ancestor", "origin/main", "HEAD",
        cwd=cwd,
    )

    if already_up_to_date:
        _log.info("rebase_onto_main: branch already contains origin/main — no-op")
        emit_builtin_effect(ctx, "rebase_onto_main", "rebase", result="up_to_date")
        return

    old_sha = _get_sha(cwd, "HEAD")
    main_sha = _get_sha(cwd, "origin/main")

    rebase_result = subprocess.run(
        ["git", "rebase", "origin/main"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )

    if rebase_result.returncode != 0:
        conflicting = _get_conflicting_files(cwd)

        # Abort to restore clean pre-rebase state.
        subprocess.run(
            ["git", "rebase", "--abort"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )

        files_str = ", ".join(conflicting) if conflicting else "(unknown — check git status)"
        raise RuntimeError(
            f"git rebase origin/main produced conflicts in: {files_str}. "
            "Resolve conflicts manually and re-run."
        )

    new_sha = _get_sha(cwd, "HEAD")

    _log.info(
        "rebase_onto_main: rebased onto origin/main (%s): %s → %s",
        main_sha[:8],
        old_sha[:8],
        new_sha[:8],
    )
    emit_builtin_effect(
        ctx,
        "rebase_onto_main",
        "rebase",
        result="rebased",
        from_sha=old_sha,
        to_sha=new_sha,
        onto_sha=main_sha,
    )
