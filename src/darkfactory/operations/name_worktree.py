"""Built-in: name_worktree — put a WorktreeState with the desired branch name."""

from __future__ import annotations

from darkfactory.engine import WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.workflow import RunContext


@builtin("name_worktree")
def name_worktree(
    ctx: RunContext,
    *,
    branch: str,
    base_ref: str = "main",
) -> None:
    """Put a WorktreeState with the desired branch name (resolved via format_string).

    Placed before ``ensure_worktree`` in workflow definitions to make
    naming explicit. ``ensure_worktree`` reads the WorktreeState if
    present and uses the branch name from it.
    """
    resolved_branch = ctx.format_string(branch)
    resolved_base = ctx.format_string(base_ref)

    ctx.state.put(WorktreeState(branch=resolved_branch, base_ref=resolved_base))
    ctx.logger.info(
        "name_worktree: branch=%s base_ref=%s", resolved_branch, resolved_base
    )
