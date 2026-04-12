"""Built-in: reply_pr_comments — post bot replies to addressed PR threads.

Runs after ``commit`` and ``push_branch`` in the rework workflow.  Only
executes when rework state has ``reply_to_comments=True``.  Parses structured
reply notes from the agent output and posts each one as a GitHub comment reply
prefixed with ``[harness] addressed in {commit_sha}: ``.

Failures are logged as warnings and do not fail the rework run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run
from darkfactory.event_log import emit_builtin_effect
from darkfactory.engine import AgentResult, ReworkState
from darkfactory.utils.git import GitErr, Ok, Timeout, git_run
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
        case Timeout():
            _log.warning("reply_pr_comments: rev-parse timed out")
            return None


@builtin("reply_pr_comments")
def reply_pr_comments(ctx: ExecutionContext) -> None:
    """Post bot replies to addressed PR comment threads.

    No-op when:

    - Rework state not present or ``reply_to_comments`` is False
    - No PR number in rework state
    - No agent output in PhaseState
    """
    rework = ctx.state.get(ReworkState, ReworkState())

    if not rework.reply_to_comments:
        _log.debug("reply_pr_comments: --reply-to-comments not set, skipping")
        return

    if rework.pr_number is None:
        ctx.logger.warning(
            "reply_pr_comments: pr_number not set in ReworkState, cannot post replies"
        )
        return

    agent_output = ""
    if ctx.state.has(AgentResult):
        agent_output = ctx.state.get(AgentResult).stdout
    if not agent_output:
        _log.info("reply_pr_comments: no agent output to parse, skipping")
        return

    from darkfactory.pr_comments import parse_agent_replies, post_comment_replies

    replies = parse_agent_replies(agent_output)
    if not replies:
        _log.info("reply_pr_comments: no reply notes found in agent output")
        return

    if _log_dry_run(
        ctx, f"would post {len(replies)} reply/replies to PR #{rework.pr_number}"
    ):
        for reply in replies:
            ctx.logger.info(
                "[dry-run]   thread=%s note=%r", reply.thread_id, reply.body
            )
        return

    commit_sha = _get_head_sha(str(ctx.cwd)) or "unknown"

    results = post_comment_replies(
        pr_number=rework.pr_number,
        replies=replies,
        threads=rework.review_threads or [],
        commit_sha=commit_sha,
        repo_root=ctx.repo_root,
    )

    success_count = sum(1 for _, ok in results if ok)
    fail_count = len(results) - success_count

    ctx.logger.info(
        "reply_pr_comments: posted %d/%d replies to PR #%d",
        success_count,
        len(results),
        rework.pr_number,
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
            "pr_number": rework.pr_number,
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
        },
    )
