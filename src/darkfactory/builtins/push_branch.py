"""Built-in: push_branch — push the current branch to origin with upstream tracking."""

from __future__ import annotations

import subprocess

from darkfactory.builtins._registry import builtin
from darkfactory.workflow import ExecutionContext


@builtin("push_branch")
def push_branch(ctx: ExecutionContext) -> None:
    """Push the current branch to origin with upstream tracking.

    Runs ``git push -u origin {branch}`` inside the worktree. Required
    before :func:`create_pr` because ``gh pr create --base`` needs the
    remote to exist.
    """
    cmd = ["git", "push", "-u", "origin", ctx.branch_name]

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return

    subprocess.run(
        cmd,
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )
