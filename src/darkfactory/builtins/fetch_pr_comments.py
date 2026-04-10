"""Built-in: fetch_pr_comments — load unresolved PR review threads into context."""

from __future__ import annotations

import logging

from darkfactory.builtins._registry import builtin
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("fetch_pr_comments")
def fetch_pr_comments(ctx: ExecutionContext) -> None:
    """Fetch unresolved PR review threads and store them on the context.

    If ``ctx.review_threads`` is already populated (e.g. pre-fetched by
    ``cmd_rework --execute``), this is a no-op — threads are used as-is.

    When threads are not yet fetched, ``ctx.pr_number`` must be set.
    The builtin calls ``pr_comments.fetch_pr_comments`` to retrieve all
    unresolved threads via the ``gh`` CLI and stores the result on
    ``ctx.review_threads``.
    """
    if ctx.review_threads is not None:
        _log.debug(
            "fetch_pr_comments: %d thread(s) already loaded, skipping fetch",
            len(ctx.review_threads),
        )
        return

    if ctx.dry_run:
        pr_label = f"#{ctx.pr_number}" if ctx.pr_number is not None else "<pr>"
        ctx.logger.info("[dry-run] would fetch PR comments for %s", pr_label)
        ctx.review_threads = []
        return

    if ctx.pr_number is None:
        raise RuntimeError(
            "fetch_pr_comments builtin: ctx.pr_number must be set before "
            "this builtin can fetch PR review threads"
        )

    from darkfactory.pr_comments import CommentFilters
    from darkfactory.pr_comments import fetch_pr_comments as _fetch

    threads = _fetch(ctx.pr_number, filters=CommentFilters())
    ctx.review_threads = threads
    _log.info(
        "fetch_pr_comments: fetched %d thread(s) for PR #%d",
        len(threads),
        ctx.pr_number,
    )

    if ctx.event_writer:
        ctx.event_writer.emit(
            "task",
            "builtin_effect",
            task="fetch_pr_comments",
            effect="fetch",
            detail={"pr_number": ctx.pr_number, "thread_count": len(threads)},
        )
