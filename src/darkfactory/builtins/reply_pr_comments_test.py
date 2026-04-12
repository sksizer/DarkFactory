"""Tests for reply_pr_comments builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.builtins.reply_pr_comments import reply_pr_comments
from darkfactory.pr_comments import ReviewThread
from darkfactory.utils._result import Ok
from darkfactory.utils.github._types import GhErr


def _default_threads() -> list[ReviewThread]:
    """Default threads matching the IC_001 reference in _VALID_OUTPUT."""
    return [
        ReviewThread(
            thread_id="IC_001",
            author="alice",
            path="src/foo.py",
            line=1,
            body="original comment",
            posted_at="2026-04-07T10:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
            reply_target_id="999001",
        )
    ]


def _make_ctx(
    *,
    reply_to_comments: bool = True,
    pr_number: int | None = 42,
    agent_output: str | None = None,
    dry_run: bool = False,
    cwd: Path | None = None,
    repo_root: Path | None = None,
    review_threads: list[ReviewThread] | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.reply_to_comments = reply_to_comments
    ctx.pr_number = pr_number
    ctx.agent_output = agent_output
    ctx.dry_run = dry_run
    ctx.cwd = cwd or Path("/tmp/worktree")
    ctx.repo_root = repo_root or Path("/tmp/repo")
    ctx.event_writer = None
    ctx.review_threads = (
        review_threads if review_threads is not None else _default_threads()
    )
    return ctx


_VALID_OUTPUT = (
    "Some work done.\n\n"
    "```json-reply-notes\n"
    '[{"thread_id": "IC_001", "note": "Addressed: renamed the method."}]\n'
    "```\n\n"
    "PRD_EXECUTE_OK: PRD-225.5"
)


# ---------- opt-in gating ----------


def test_skips_when_reply_to_comments_false() -> None:
    ctx = _make_ctx(reply_to_comments=False, agent_output=_VALID_OUTPUT)
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()


def test_skips_when_no_pr_number() -> None:
    ctx = _make_ctx(pr_number=None, agent_output=_VALID_OUTPUT)
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()
    ctx.logger.warning.assert_called()


def test_skips_when_no_agent_output() -> None:
    ctx = _make_ctx(agent_output=None)
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()


def test_skips_when_agent_output_empty_string() -> None:
    ctx = _make_ctx(agent_output="")
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()


# ---------- dry-run ----------


def test_dry_run_logs_without_posting() -> None:
    ctx = _make_ctx(dry_run=True, agent_output=_VALID_OUTPUT)
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()
    ctx.logger.info.assert_called()
    # Check dry-run message appears
    all_calls = " ".join(str(c) for c in ctx.logger.info.call_args_list)
    assert "[dry-run]" in all_calls


# ---------- successful posting ----------


def test_posts_replies_on_success(tmp_path: Path) -> None:
    ctx = _make_ctx(agent_output=_VALID_OUTPUT, repo_root=tmp_path, cwd=tmp_path)

    import subprocess

    sha_result = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="abc1234\n", stderr=""
    )

    with (
        patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=sha_result,
        ),
        patch(
            "darkfactory.pr_comments.post_reply",
            return_value=Ok(None),
        ),
    ):
        reply_pr_comments(ctx)

    ctx.logger.info.assert_called()


def test_failure_does_not_raise(tmp_path: Path) -> None:
    ctx = _make_ctx(agent_output=_VALID_OUTPUT, repo_root=tmp_path, cwd=tmp_path)

    import subprocess

    sha_result = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="abc1234\n", stderr=""
    )

    with (
        patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=sha_result,
        ),
        patch(
            "darkfactory.pr_comments.post_reply",
            return_value=GhErr(1, "", "rate limit exceeded", ["gh", "api"]),
        ),
    ):
        # Must NOT raise even on failure
        reply_pr_comments(ctx)

    ctx.logger.warning.assert_called()


def test_no_replies_in_output_is_silent(tmp_path: Path) -> None:
    ctx = _make_ctx(
        agent_output="Some output with no reply notes block.\nPRD_EXECUTE_OK: PRD-225.5",
        repo_root=tmp_path,
        cwd=tmp_path,
    )
    with patch("darkfactory.pr_comments.post_reply") as mock_reply:
        reply_pr_comments(ctx)
    mock_reply.assert_not_called()
