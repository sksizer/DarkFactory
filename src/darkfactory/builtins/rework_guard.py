"""Built-in: check_rework_guard — detect no-change rework loops.

Checks whether the current rework cycle produced any file modifications.
If no changes are present, records a no-change cycle in the rework guard
and either warns (below threshold) or raises :class:`RuntimeError`
(at/above threshold) to block the commit and push steps.
"""

from __future__ import annotations

import logging
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_task_event
from darkfactory.rework_guard import ReworkGuard
from darkfactory.utils.git import GitErr, Ok, Timeout, git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


def _has_changes(cwd: str) -> bool:
    """Return True if there are any staged or unstaged changes in the worktree.

    Returns False if the directory is not a git worktree or git errors for any
    reason, preserving the original non-raising semantics.
    """
    match git_run("status", "--porcelain", cwd=Path(cwd)):
        case Ok(stdout=output):
            return bool(output.strip())
        case GitErr() | Timeout():
            return False


@builtin("check_rework_guard")
def check_rework_guard(ctx: ExecutionContext) -> None:
    """Detect no-change rework loops and block after N consecutive attempts.

    Runs ``git status --porcelain`` to determine whether the rework cycle
    produced any changes. Updates the guard state in
    ``.darkfactory/state/rework-guard.json`` and either warns (below the
    threshold) or raises :class:`RuntimeError` (at threshold) to block the
    commit and push steps.

    In dry-run mode, logs what would happen without updating guard state.
    """
    if _log_dry_run(ctx, "check_rework_guard: would check git status"):
        return

    had_changes = _has_changes(str(ctx.cwd))

    guard = ReworkGuard(ctx.repo_root)
    outcome = guard.record_outcome(ctx.prd.id, had_changes=had_changes)

    if had_changes:
        ctx.logger.info(
            "check_rework_guard: %s produced changes, guard counter reset",
            ctx.prd.id,
        )
        emit_task_event(
            ctx,
            "rework_guard",
            prd_id=ctx.prd.id,
            had_changes=True,
            blocked=False,
            consecutive_no_change=0,
        )
        return

    # No changes — log and potentially block.
    if outcome.warning:
        if outcome.blocked:
            _log.error("REWORK LOOP DETECTED: %s", outcome.warning)
        else:
            _log.warning("rework no-change: %s", outcome.warning)

    emit_task_event(
        ctx,
        "rework_guard",
        prd_id=ctx.prd.id,
        had_changes=False,
        blocked=outcome.blocked,
        consecutive_no_change=outcome.consecutive_no_change,
        warning=outcome.warning,
    )

    if outcome.blocked:
        raise RuntimeError(
            f"REWORK LOOP BLOCKED: {ctx.prd.id} has {outcome.consecutive_no_change} "
            f"consecutive rework cycle(s) with no changes. "
            f"Manual intervention required."
        )
