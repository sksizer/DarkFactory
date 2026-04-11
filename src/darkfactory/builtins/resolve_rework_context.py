"""Built-in: resolve_rework_context — discover worktree, PR, guard state, threads.

First task in the rework workflow. Populates ``ctx.worktree_path``,
``ctx.cwd``, ``ctx.pr_number``, and ``ctx.review_threads`` so that every
subsequent task (fast-forward, rebase, agent invoke, commit, push,
reply) can run against a concrete worktree and a concrete PR.

When the CLI has already pre-discovered the rework state (the default
path through ``prd rework``), the builtin is a no-op: it sees the ctx
fields populated and returns immediately. The builtin exists to keep
the workflow self-contained — any caller that constructs a bare
ExecutionContext (tests, future non-CLI invokers) still gets a
working rework run without having to duplicate the discovery logic.
"""

from __future__ import annotations

import logging

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.pr_comments import CommentFilters
from darkfactory.rework_context import ReworkError, discover_rework_context
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("resolve_rework_context")
def resolve_rework_context(ctx: ExecutionContext) -> None:
    """Discover rework pre-conditions and populate the context.

    No-op when ``ctx.worktree_path`` and ``ctx.review_threads`` are
    already set (the CLI pre-discovered). Otherwise calls
    :func:`~darkfactory.rework_context.discover_rework_context` with
    ``ctx.comment_filters`` (or an empty filter set when unset) and
    stores the result on the context.

    :class:`~darkfactory.rework_context.ReworkError` from discovery is
    re-raised as ``RuntimeError`` so the runner records the failed step
    with the original message.
    """
    if ctx.worktree_path is not None and ctx.review_threads is not None:
        _log.debug(
            "resolve_rework_context: ctx already populated "
            "(%d thread(s), worktree %s) — skipping discovery",
            len(ctx.review_threads),
            ctx.worktree_path,
        )
        return

    filters = ctx.comment_filters or CommentFilters()

    if _log_dry_run(
        ctx,
        f"resolve_rework_context: would discover worktree, PR, and review "
        f"threads for {ctx.prd.id}",
    ):
        if ctx.review_threads is None:
            ctx.review_threads = []
        return

    try:
        discovered = discover_rework_context(
            ctx.prd,
            ctx.repo_root,
            comment_filters=filters,
            reply_to_comments=ctx.reply_to_comments,
        )
    except ReworkError as exc:
        raise RuntimeError(f"resolve_rework_context: {exc}") from exc

    ctx.worktree_path = discovered.worktree_path
    ctx.cwd = discovered.worktree_path
    ctx.pr_number = discovered.pr_number
    ctx.review_threads = discovered.review_threads

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
