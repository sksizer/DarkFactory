"""Built-in: push_branch — push the current branch to origin with upstream tracking."""

from __future__ import annotations

import logging

from darkfactory.engine import CodeEnv, WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import RunContext

_log = logging.getLogger(__name__)


@builtin("push_branch")
def push_branch(ctx: RunContext) -> None:
    """Push the current branch to origin with upstream tracking.

    Reads branch name from ``WorktreeState`` in ``ctx.state``.
    Runs ``git push -u origin {branch}`` inside the worktree. Required
    before :func:`create_pr` because ``gh pr create --base`` needs the
    remote to exist.
    """
    wt = ctx.state.get(WorktreeState)
    env = ctx.state.get(CodeEnv)

    if _log_dry_run(ctx, " ".join(["git", "push", "-u", "origin", wt.branch])):
        return

    match git_run("push", "-u", "origin", wt.branch, cwd=env.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stdout=out, stderr=err):
            detail = f"git push failed (exit {code}):\nstdout: {out}\nstderr: {err}"
            _log.error(detail)
            raise RuntimeError(detail)

    emit_builtin_effect(ctx, "push_branch", "push", detail={"branch": wt.branch})
