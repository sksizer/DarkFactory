"""Built-in: push_branch — push the current branch to origin with upstream tracking."""

from __future__ import annotations

import logging
import subprocess

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.git_ops import git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("push_branch")
def push_branch(ctx: ExecutionContext) -> None:
    """Push the current branch to origin with upstream tracking.

    Runs ``git push -u origin {branch}`` inside the worktree. Required
    before :func:`create_pr` because ``gh pr create --base`` needs the
    remote to exist.
    """
    if _log_dry_run(ctx, " ".join(["git", "push", "-u", "origin", ctx.branch_name])):
        return

    try:
        git_run("push", "-u", "origin", ctx.branch_name, cwd=ctx.cwd)
    except subprocess.CalledProcessError as exc:
        detail = (
            f"git push failed (exit {exc.returncode}):"
            f"\nstdout: {exc.stdout}"
            f"\nstderr: {exc.stderr}"
        )
        _log.error(detail)
        raise RuntimeError(detail) from exc

    emit_builtin_effect(ctx, "push_branch", "push", detail={"branch": ctx.branch_name})
