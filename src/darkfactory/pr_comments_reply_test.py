"""Tests for CommentReply, parse_agent_replies, and post_comment_replies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.pr_comments import (
    CommentReply,
    ReviewThread,
    parse_agent_replies,
    post_comment_replies,
)


def _make_thread(thread_id: str, reply_target_id: str | None) -> ReviewThread:
    """Minimal ReviewThread for post_comment_replies tests."""
    return ReviewThread(
        thread_id=thread_id,
        author="alice",
        path="src/foo.py" if reply_target_id else None,
        line=1 if reply_target_id else None,
        body="body",
        posted_at="2026-04-07T10:00:00Z",
        is_resolved=False,
        replies=[],
        review_state=None,
        reply_target_id=reply_target_id,
    )


# ---------- parse_agent_replies ----------


def test_parse_agent_replies_valid_single() -> None:
    output = """
Some agent output here.

```json-reply-notes
[{"thread_id": "IC_abc123", "note": "Addressed: renamed the method."}]
```

PRD_EXECUTE_OK: PRD-225.5
"""
    replies = parse_agent_replies(output)
    assert len(replies) == 1
    assert replies[0].thread_id == "IC_abc123"
    assert replies[0].body == "Addressed: renamed the method."


def test_parse_agent_replies_multiple() -> None:
    output = (
        "```json-reply-notes\n"
        '[{"thread_id": "IC_001", "note": "Fixed."}, '
        '{"thread_id": "IC_002", "note": "Disagree: not a bug."}]\n'
        "```"
    )
    replies = parse_agent_replies(output)
    assert len(replies) == 2
    assert replies[0].thread_id == "IC_001"
    assert replies[1].thread_id == "IC_002"
    assert replies[1].body == "Disagree: not a bug."


def test_parse_agent_replies_missing_block() -> None:
    output = "Agent did stuff but emitted no reply notes block."
    replies = parse_agent_replies(output)
    assert replies == []


def test_parse_agent_replies_invalid_json() -> None:
    output = "```json-reply-notes\nnot valid json\n```"
    replies = parse_agent_replies(output)
    assert replies == []


def test_parse_agent_replies_not_a_list() -> None:
    output = '```json-reply-notes\n{"thread_id": "x", "note": "y"}\n```'
    replies = parse_agent_replies(output)
    assert replies == []


def test_parse_agent_replies_missing_fields_skipped() -> None:
    output = (
        "```json-reply-notes\n"
        '[{"thread_id": "IC_001"}, {"thread_id": "IC_002", "note": "OK."}]\n'
        "```"
    )
    replies = parse_agent_replies(output)
    # First item missing "note" is skipped
    assert len(replies) == 1
    assert replies[0].thread_id == "IC_002"


def test_parse_agent_replies_non_dict_items_skipped() -> None:
    output = (
        "```json-reply-notes\n"
        '["not-a-dict", {"thread_id": "IC_001", "note": "OK."}]\n'
        "```"
    )
    replies = parse_agent_replies(output)
    assert len(replies) == 1
    assert replies[0].thread_id == "IC_001"


def test_parse_agent_replies_empty_array() -> None:
    output = "```json-reply-notes\n[]\n```"
    replies = parse_agent_replies(output)
    assert replies == []


# ---------- post_comment_replies ----------


def _make_mock_run(returncode: int = 0, stderr: str = "") -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stderr = stderr
    mock.stdout = "{}"
    return mock


def test_post_comment_replies_success(tmp_path: Path) -> None:
    replies = [CommentReply(thread_id="IC_001", body="Fixed it.")]
    threads = [_make_thread("IC_001", reply_target_id="555001")]
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        mock_run.return_value = _make_mock_run(returncode=0)
        results = post_comment_replies(
            pr_number=42,
            replies=replies,
            threads=threads,
            commit_sha="abc1234",
            repo_root=tmp_path,
        )

    assert results == [("IC_001", True)]
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    # Verify the URL uses the numeric reply_target_id, not the thread_id
    url_arg = next(a for a in call_args if a.startswith("repos/") and "/replies" in a)
    assert "/comments/555001/replies" in url_arg
    assert "IC_001" not in url_arg
    body_arg = next(a for a in call_args if a.startswith("body="))
    assert body_arg.startswith("body=[harness] addressed in abc1234: Fixed it.")


def test_post_comment_replies_prefix_format(tmp_path: Path) -> None:
    replies = [CommentReply(thread_id="IC_999", body="Renamed the variable.")]
    threads = [_make_thread("IC_999", reply_target_id="555999")]
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        mock_run.return_value = _make_mock_run(returncode=0)
        post_comment_replies(
            pr_number=7,
            replies=replies,
            threads=threads,
            commit_sha="deadbeef",
            repo_root=tmp_path,
        )

    call_args = mock_run.call_args[0][0]
    body_arg = next(a for a in call_args if a.startswith("body="))
    assert body_arg == "body=[harness] addressed in deadbeef: Renamed the variable."


def test_post_comment_replies_failure_returns_false(tmp_path: Path) -> None:
    replies = [CommentReply(thread_id="IC_bad", body="Something.")]
    threads = [_make_thread("IC_bad", reply_target_id="555bad")]
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        mock_run.return_value = _make_mock_run(returncode=1, stderr="permission denied")
        results = post_comment_replies(
            pr_number=1,
            replies=replies,
            threads=threads,
            commit_sha="sha1",
            repo_root=tmp_path,
        )

    assert results == [("IC_bad", False)]


def test_post_comment_replies_exception_returns_false(tmp_path: Path) -> None:
    replies = [CommentReply(thread_id="IC_exc", body="Something.")]
    threads = [_make_thread("IC_exc", reply_target_id="555exc")]
    with patch(
        "darkfactory.utils.github._cli.subprocess.run", side_effect=OSError("no gh")
    ):
        results = post_comment_replies(
            pr_number=1,
            replies=replies,
            threads=threads,
            commit_sha="sha1",
            repo_root=tmp_path,
        )

    assert results == [("IC_exc", False)]


def test_post_comment_replies_multiple_mixed(tmp_path: Path) -> None:
    replies = [
        CommentReply(thread_id="IC_ok", body="Fixed."),
        CommentReply(thread_id="IC_fail", body="Done."),
    ]
    threads = [
        _make_thread("IC_ok", reply_target_id="5550"),
        _make_thread("IC_fail", reply_target_id="5551"),
    ]
    responses = [_make_mock_run(0), _make_mock_run(1, "rate limit")]
    with patch("darkfactory.utils.github._cli.subprocess.run", side_effect=responses):
        results = post_comment_replies(
            pr_number=5,
            replies=replies,
            threads=threads,
            commit_sha="abc",
            repo_root=tmp_path,
        )

    assert results == [("IC_ok", True), ("IC_fail", False)]


def test_post_comment_replies_empty(tmp_path: Path) -> None:
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        results = post_comment_replies(
            pr_number=1,
            replies=[],
            threads=[],
            commit_sha="sha",
            repo_root=tmp_path,
        )
    assert results == []
    mock_run.assert_not_called()


def test_post_comment_replies_unknown_thread_id_skipped(tmp_path: Path) -> None:
    """An agent-supplied thread_id not in the fetched threads is logged and skipped."""
    replies = [CommentReply(thread_id="IC_ghost", body="Done.")]
    threads = [_make_thread("IC_real", reply_target_id="5555")]
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        results = post_comment_replies(
            pr_number=1,
            replies=replies,
            threads=threads,
            commit_sha="sha",
            repo_root=tmp_path,
        )
    assert results == [("IC_ghost", False)]
    mock_run.assert_not_called()


def test_post_comment_replies_no_reply_target_skipped(tmp_path: Path) -> None:
    """A thread with no reply_target_id (review summary / issue comment) is skipped."""
    replies = [CommentReply(thread_id="review-1", body="Thanks.")]
    threads = [_make_thread("review-1", reply_target_id=None)]
    with patch("darkfactory.utils.github._cli.subprocess.run") as mock_run:
        results = post_comment_replies(
            pr_number=1,
            replies=replies,
            threads=threads,
            commit_sha="sha",
            repo_root=tmp_path,
        )
    assert results == [("review-1", False)]
    mock_run.assert_not_called()
