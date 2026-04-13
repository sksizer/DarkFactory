"""Built-in: set_status — rewrite the PRD's status frontmatter field."""

from __future__ import annotations

from darkfactory import model as prd_module
from darkfactory.engine import CodeEnv, PrdWorkflowRun, WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.timestamps import today_iso
from darkfactory.workflow import RunContext, Status


@builtin("set_status")
def set_status(ctx: RunContext, *, to: Status) -> None:
    """Rewrite the PRD's ``status:`` frontmatter field inside the worktree."""
    prd_run = ctx.state.get(PrdWorkflowRun)
    wt = ctx.state.get(WorktreeState)
    env = ctx.state.get(CodeEnv)

    if _log_dry_run(
        ctx,
        f"set status of {prd_run.prd.id}: {prd_run.prd.status} -> {to} (worktree={wt.worktree_path})",
    ):
        return

    if wt.worktree_path is None:
        raise RuntimeError(
            "set_status requires a worktree; ensure_worktree must run first"
        )

    relative = prd_run.prd.path.relative_to(env.repo_root)
    target = wt.worktree_path / relative
    old_status = prd_run.prd.status
    prd_module.set_status_at(target, to)
    # Mirror the field updates onto the in-memory PRD so subsequent
    # builtins see the new status without re-loading from disk.
    prd_run.prd.status = to
    prd_run.prd.updated = today_iso()

    emit_builtin_effect(
        ctx, "set_status", "set_status", detail={"from": old_status, "to": to}
    )
