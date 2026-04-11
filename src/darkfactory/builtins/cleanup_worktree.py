"""cleanup_worktree builtin — remove a git worktree after a successful run."""

from __future__ import annotations

import logging

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.utils.git import git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("cleanup_worktree")
def cleanup_worktree(ctx: ExecutionContext) -> None:
    """Remove the worktree after a successful run.

    Idempotent — if the worktree is already gone, logs and returns.
    Normally skipped during chain execution so downstream worktrees
    can base on this branch; called explicitly via ``prd cleanup``
    after the whole chain is done.
    """
    if ctx.worktree_path is None:
        ctx.logger.info("cleanup_worktree: no worktree path set, skipping")
        return

    if not ctx.worktree_path.exists():
        ctx.logger.info(
            "cleanup_worktree: %s already gone, skipping", ctx.worktree_path
        )
        return

    if _log_dry_run(ctx, f"git -C {ctx.repo_root} worktree remove {ctx.worktree_path}"):
        return

    git_run("worktree", "remove", str(ctx.worktree_path), cwd=ctx.repo_root)
