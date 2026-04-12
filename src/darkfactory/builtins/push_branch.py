"""Built-in: push_branch — push the current branch to origin with upstream tracking."""

from __future__ import annotations

import logging

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import GitErr, Ok, git_run
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

    match git_run("push", "-u", "origin", ctx.branch_name, cwd=ctx.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stdout=out, stderr=err):
            detail = f"git push failed (exit {code}):\nstdout: {out}\nstderr: {err}"
            _log.error(detail)
            raise RuntimeError(detail)

    emit_builtin_effect(ctx, "push_branch", "push", detail={"branch": ctx.branch_name})
