"""Built-in: resolve_rework_context — discover worktree, PR, guard state, threads.

First task in the rework workflow. Populates ``ctx.worktree_path``,
``ctx.cwd``, and stores a :class:`ReworkState` in ``ctx.state`` with
``pr_number`` and ``review_threads`` so that every subsequent task
can run against a concrete worktree and a concrete PR.

When the CLI has already pre-discovered the rework state (the default
path through ``prd rework``), the builtin is a no-op: it sees the
ReworkState in ctx.state and returns immediately.
"""

from __future__ import annotations

import logging

from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.engine import ReworkState
from darkfactory.utils.github.pr.comments import CommentFilters
from darkfactory.rework.context import ReworkError, discover_rework_context
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("resolve_rework_context")
def resolve_rework_context(ctx: ExecutionContext) -> None:
    """Discover rework pre-conditions and populate the context.

    No-op when ``ctx.worktree_path`` is set and ``ReworkState`` has
    ``review_threads`` populated (the CLI pre-discovered). Otherwise
    calls :func:`~darkfactory.rework.context.discover_rework_context`
    and stores the result in PhaseState.
    """
    rework = ctx.state.get(ReworkState, ReworkState())

    if ctx.worktree_path is not None and rework.review_threads is not None:
        _log.debug(
            "resolve_rework_context: ctx already populated "
            "(%d thread(s), worktree %s) — skipping discovery",
            len(rework.review_threads),
            ctx.worktree_path,
        )
        return

    filters = rework.comment_filters or CommentFilters()

    if _log_dry_run(
        ctx,
        f"resolve_rework_context: would discover worktree, PR, and review "
        f"threads for {ctx.prd.id}",
    ):
        if rework.review_threads is None:
            ctx.state.put(
                ReworkState(
                    pr_number=rework.pr_number,
                    review_threads=[],
                    reply_to_comments=rework.reply_to_comments,
                    comment_filters=rework.comment_filters,
                )
            )
        return

    try:
        discovered = discover_rework_context(
            ctx.prd,
            ctx.repo_root,
            comment_filters=filters,
            reply_to_comments=rework.reply_to_comments,
        )
    except ReworkError as exc:
        raise RuntimeError(f"resolve_rework_context: {exc}") from exc

    ctx.worktree_path = discovered.worktree_path
    ctx.cwd = discovered.worktree_path
    ctx.state.put(
        ReworkState(
            pr_number=discovered.pr_number,
            review_threads=discovered.review_threads,
            reply_to_comments=rework.reply_to_comments,
            comment_filters=discovered.comment_filters,
        )
    )

    _log.info(
        "resolve_rework_context: %s → worktree=%s, PR=#%d, threads=%d",
        ctx.prd.id,
        discovered.worktree_path,
        discovered.pr_number,
        len(discovered.review_threads),
    )

    emit_builtin_effect(
        ctx,
        "resolve_rework_context",
        "resolve",
        detail={
            "prd_id": ctx.prd.id,
            "worktree_path": str(discovered.worktree_path),
            "pr_number": discovered.pr_number,
            "thread_count": len(discovered.review_threads),
        },
    )
