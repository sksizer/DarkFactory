"""Built-in: fetch_pr_comments — load unresolved PR review threads into PhaseState."""

from __future__ import annotations

import logging

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.phase_state import ReworkState
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("fetch_pr_comments")
def fetch_pr_comments(ctx: ExecutionContext) -> None:
    """Fetch unresolved PR review threads and store them in PhaseState.

    If ``ReworkState`` already has ``review_threads`` populated (e.g.
    pre-fetched by ``cmd_rework --execute``), this is a no-op.

    When threads are not yet fetched, ``pr_number`` must be set in
    ``ReworkState``. The builtin calls ``pr_comments.fetch_pr_comments``
    to retrieve all unresolved threads and updates ``ReworkState``.
    """
    rework = ctx.state.get(ReworkState, ReworkState())

    if rework.review_threads is not None:
        _log.debug(
            "fetch_pr_comments: %d thread(s) already loaded, skipping fetch",
            len(rework.review_threads),
        )
        return

    pr_label = f"#{rework.pr_number}" if rework.pr_number is not None else "<pr>"
    if _log_dry_run(ctx, f"would fetch PR comments for {pr_label}"):
        ctx.state.put(
            ReworkState(
                pr_number=rework.pr_number,
                review_threads=[],
                reply_to_comments=rework.reply_to_comments,
                comment_filters=rework.comment_filters,
            )
        )
        return

    if rework.pr_number is None:
        raise RuntimeError(
            "fetch_pr_comments builtin: pr_number must be set in ReworkState before "
            "this builtin can fetch PR review threads"
        )

    from darkfactory.pr_comments import CommentFilters
    from darkfactory.pr_comments import fetch_pr_comments as _fetch

    threads = _fetch(rework.pr_number, filters=CommentFilters())
    ctx.state.put(
        ReworkState(
            pr_number=rework.pr_number,
            review_threads=threads,
            reply_to_comments=rework.reply_to_comments,
            comment_filters=rework.comment_filters,
        )
    )
    _log.info(
        "fetch_pr_comments: fetched %d thread(s) for PR #%d",
        len(threads),
        rework.pr_number,
    )

    emit_builtin_effect(
        ctx,
        "fetch_pr_comments",
        "fetch",
        detail={"pr_number": rework.pr_number, "thread_count": len(threads)},
    )
