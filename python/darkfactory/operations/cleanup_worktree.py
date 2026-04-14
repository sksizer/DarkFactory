"""cleanup_worktree builtin — remove a git worktree after a successful run."""

from __future__ import annotations

import logging

from darkfactory.engine import CodeEnv, WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import RunContext

_log = logging.getLogger(__name__)


@builtin("cleanup_worktree")
def cleanup_worktree(ctx: RunContext) -> None:
    """Remove the worktree after a successful run."""
    wt = ctx.state.get(WorktreeState, WorktreeState(branch=""))
    env = ctx.state.get(CodeEnv)

    if wt.worktree_path is None:
        ctx.logger.info("cleanup_worktree: no worktree path set, skipping")
        return

    if not wt.worktree_path.exists():
        ctx.logger.info("cleanup_worktree: %s already gone, skipping", wt.worktree_path)
        return

    if _log_dry_run(ctx, f"git -C {env.repo_root} worktree remove {wt.worktree_path}"):
        return

    match git_run("worktree", "remove", str(wt.worktree_path), cwd=env.repo_root):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git worktree remove failed (exit {code}):\n{err}")
