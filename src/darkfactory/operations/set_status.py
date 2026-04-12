"""Built-in: set_status — rewrite the PRD's status frontmatter field."""

from __future__ import annotations

from darkfactory import model as prd_module
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.timestamps import today_iso
from darkfactory.workflow import ExecutionContext, Status


@builtin("set_status")
def set_status(ctx: ExecutionContext, *, to: Status) -> None:
    """Rewrite the PRD's ``status:`` frontmatter field inside the worktree.

    Targets the worktree's copy of the PRD file, never the source repo.
    The source repo's working tree must remain untouched by ``prd run`` —
    status transitions live on the PRD's worktree branch and only reach
    the source repo via PR merge (see PRD-213).

    Uses :func:`darkfactory.prd.set_status_at`, which surgically rewrites
    only the ``status:`` and ``updated:`` lines so the resulting commit
    diff is two lines, not the whole frontmatter block.
    """
    if _log_dry_run(
        ctx,
        f"set status of {ctx.prd.id}: {ctx.prd.status} -> {to} (worktree={ctx.worktree_path})",
    ):
        return

    if ctx.worktree_path is None:
        raise RuntimeError(
            "set_status requires a worktree; ensure_worktree must run first"
        )

    relative = ctx.prd.path.relative_to(ctx.repo_root)
    target = ctx.worktree_path / relative
    old_status = ctx.prd.status
    prd_module.set_status_at(target, to)
    # Mirror the field updates onto the in-memory PRD so subsequent
    # builtins see the new status without re-loading from disk.
    ctx.prd.status = to
    ctx.prd.updated = today_iso()

    emit_builtin_effect(
        ctx, "set_status", "set_status", detail={"from": old_status, "to": to}
    )
