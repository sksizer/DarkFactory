"""cleanup_worktree builtin — remove a git worktree after a successful run."""

from __future__ import annotations

import logging
import subprocess

from darkfactory.builtins._registry import builtin
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

    cmd = [
        "git",
        "-C",
        str(ctx.repo_root),
        "worktree",
        "remove",
        str(ctx.worktree_path),
    ]

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return

    subprocess.run(cmd, check=True, capture_output=True, text=True)
