"""Built-in: reply_pr_comments — post bot replies to addressed PR threads.

Runs after ``commit`` and ``push_branch`` in the rework workflow.  Only
executes when ``ctx.reply_to_comments`` is True.  Parses structured reply
notes from the agent output and posts each one as a GitHub comment reply
prefixed with ``[harness] addressed in {commit_sha}: ``.

Failures are logged as warnings and do not fail the rework run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


def _get_head_sha(cwd: str) -> str | None:
    """Return the short SHA of HEAD, or None on failure."""
    match git_run("rev-parse", "--short", "HEAD", cwd=Path(cwd)):
        case Ok(stdout=output):
            return output.strip()
        case GitErr() as err:
            _log.warning("reply_pr_comments: could not resolve HEAD SHA: %s", err)
            return None


@builtin("reply_pr_comments")
def reply_pr_comments(ctx: ExecutionContext) -> None:
    """Post bot replies to addressed PR comment threads.

    No-op when:

    - ``ctx.reply_to_comments`` is False (opt-in flag not set)
    - ``ctx.pr_number`` is None (no PR to reply to)
    - ``ctx.agent_output`` is empty (no agent output to parse)

    When enabled, parses the agent's structured reply-notes block from
    ``ctx.agent_output``, resolves the current HEAD SHA as the commit
    reference, and posts each reply via ``gh api``.

    Failed posts are logged as warnings but do not raise — the rework
    run proceeds regardless.
    """
    if not ctx.reply_to_comments:
        _log.debug("reply_pr_comments: --reply-to-comments not set, skipping")
        return

    if ctx.pr_number is None:
        ctx.logger.warning(
            "reply_pr_comments: ctx.pr_number not set, cannot post replies"
        )
        return

    if not ctx.agent_output:
        _log.info("reply_pr_comments: no agent output to parse, skipping")
        return

    from darkfactory.pr_comments import parse_agent_replies, post_comment_replies

    replies = parse_agent_replies(ctx.agent_output)
    if not replies:
        _log.info("reply_pr_comments: no reply notes found in agent output")
        return

    if _log_dry_run(
        ctx, f"would post {len(replies)} reply/replies to PR #{ctx.pr_number}"
    ):
        for reply in replies:
            ctx.logger.info(
                "[dry-run]   thread=%s note=%r", reply.thread_id, reply.body
            )
        return

    commit_sha = _get_head_sha(str(ctx.cwd)) or "unknown"

    results = post_comment_replies(
        pr_number=ctx.pr_number,
        replies=replies,
        threads=ctx.review_threads or [],
        commit_sha=commit_sha,
        repo_root=ctx.repo_root,
    )

    success_count = sum(1 for _, ok in results if ok)
    fail_count = len(results) - success_count

    ctx.logger.info(
        "reply_pr_comments: posted %d/%d replies to PR #%d",
        success_count,
        len(results),
        ctx.pr_number,
    )

    if fail_count:
        ctx.logger.warning(
            "reply_pr_comments: %d reply/replies failed to post (see warnings above)",
            fail_count,
        )

    emit_builtin_effect(
        ctx,
        "reply_pr_comments",
        "reply",
        detail={
            "pr_number": ctx.pr_number,
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
        },
    )
