"""Tests for the pr_comments module.

All tests use fixture JSON (captured from a real ``gh pr view`` output shape)
so no real gh CLI or git repo is required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from darkfactory.utils.github.pr.comments import (
    CommentFilters,
    ReviewComment,
    ReviewThread,
    _apply_filters,
    _is_bot_comment,
    _parse_threads,
    fetch_pr_comments,
)


# ---------- fixture data ----------

FIXTURE_REVIEW_THREADS = [
    {
        "isResolved": False,
        "path": "src/foo.py",
        "line": 42,
        "comments": [
            {
                "id": "rt-abc",
                "databaseId": 1001,
                "author": {"login": "alice"},
                "body": "This needs a docstring.",
                "createdAt": "2026-04-07T10:00:00Z",
            },
            {
                "id": "rt-abc-reply",
                "databaseId": 1002,
                "author": {"login": "bob"},
                "body": "Working on it.",
                "createdAt": "2026-04-07T11:00:00Z",
            },
        ],
    },
    {
        "isResolved": True,
        "path": "src/bar.py",
        "line": 10,
        "comments": [
            {
                "id": "rt-resolved",
                "databaseId": 2001,
                "author": {"login": "alice"},
                "body": "Fixed already.",
                "createdAt": "2026-04-06T09:00:00Z",
            }
        ],
    },
]

FIXTURE_REVIEWS = [
    {
        "id": "review-1",
        "author": {"login": "carol"},
        "body": "Please add tests for the edge cases.",
        "submittedAt": "2026-04-07T12:00:00Z",
        "state": "CHANGES_REQUESTED",
    },
    {
        "id": "review-2",
        "author": {"login": "dave"},
        "body": "",  # empty body — should be skipped
        "submittedAt": "2026-04-07T12:30:00Z",
        "state": "APPROVED",
    },
]

FIXTURE_COMMENTS = [
    {
        "id": "comment-1",
        "author": {"login": "eve"},
        "body": "Is this intentional?",
        "createdAt": "2026-04-07T13:00:00Z",
    },
    {
        "id": "comment-bot",
        "author": {"login": "harness-bot"},
        "body": "Automated check passed.",
        "createdAt": "2026-04-07T13:01:00Z",
    },
]

FIXTURE_RAW: dict[str, Any] = {
    "reviewThreads": FIXTURE_REVIEW_THREADS,
    "reviews": FIXTURE_REVIEWS,
    "comments": FIXTURE_COMMENTS,
}


# ---------- _parse_threads ----------


def test_parse_threads_returns_review_thread_objects() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    assert all(isinstance(t, ReviewThread) for t in threads)


def test_parse_threads_inline_thread_fields() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    inline = next(t for t in threads if t.thread_id == "rt-abc")
    assert inline.author == "alice"
    assert inline.path == "src/foo.py"
    assert inline.line == 42
    assert inline.body == "This needs a docstring."
    assert inline.is_resolved is False
    assert inline.review_state is None
    assert len(inline.replies) == 1
    assert isinstance(inline.replies[0], ReviewComment)
    assert inline.replies[0].author == "bob"


def test_parse_threads_inline_thread_reply_target_id() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    inline = next(t for t in threads if t.thread_id == "rt-abc")
    # reply_target_id is the first comment's databaseId (as str) — what the
    # REST /pulls/.../comments/{id}/replies endpoint accepts.
    assert inline.reply_target_id == "1001"


def test_parse_threads_review_summary_has_no_reply_target() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    review = next(t for t in threads if t.thread_id == "review-1")
    assert review.reply_target_id is None


def test_parse_threads_issue_comment_has_no_reply_target() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    comment = next(t for t in threads if t.thread_id == "comment-1")
    assert comment.reply_target_id is None


def test_parse_threads_resolved_flag() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    resolved = next(t for t in threads if t.thread_id == "rt-resolved")
    assert resolved.is_resolved is True


def test_parse_threads_review_summary_included() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    review = next(t for t in threads if t.thread_id == "review-1")
    assert review.author == "carol"
    assert review.path is None
    assert review.line is None
    assert review.review_state == "CHANGES_REQUESTED"
    assert "edge cases" in review.body


def test_parse_threads_empty_review_body_skipped() -> None:
    """Empty review summaries (e.g. a silent approval) should be omitted."""
    threads = _parse_threads(FIXTURE_RAW)
    ids = {t.thread_id for t in threads}
    assert "review-2" not in ids


def test_parse_threads_issue_comment_included() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    comment = next(t for t in threads if t.thread_id == "comment-1")
    assert comment.author == "eve"
    assert comment.path is None
    assert comment.is_resolved is False


def test_parse_threads_empty_pr() -> None:
    """An empty PR with no comments returns an empty list."""
    threads = _parse_threads({"reviewThreads": [], "reviews": [], "comments": []})
    assert threads == []


def test_parse_threads_missing_keys() -> None:
    """Missing top-level keys default to empty lists without error."""
    threads = _parse_threads({})
    assert threads == []


# ---------- _apply_filters — resolved ----------


def test_filter_excludes_resolved_by_default() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters())
    ids = {t.thread_id for t in result}
    assert "rt-resolved" not in ids


def test_filter_includes_resolved_when_flag_set() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(include_resolved=True))
    ids = {t.thread_id for t in result}
    assert "rt-resolved" in ids


# ---------- _apply_filters — reviewer ----------


def test_filter_reviewer_keeps_only_matching_author() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(reviewer="alice"))
    assert all(t.author == "alice" for t in result)


def test_filter_reviewer_no_match_returns_empty() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(reviewer="nobody"))
    assert result == []


# ---------- _apply_filters — bot ----------


def test_filter_bot_username_excluded() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(bot_usernames=["harness-bot"]))
    ids = {t.thread_id for t in result}
    assert "comment-bot" not in ids


def test_filter_bot_harness_prefix_excluded() -> None:
    """Comments whose body starts with [harness] are excluded regardless of author."""
    threads = [
        ReviewThread(
            thread_id="x",
            author="someone",
            path=None,
            line=None,
            body="[harness] automated message",
            posted_at="2026-04-07T10:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
        )
    ]
    result = _apply_filters(threads, CommentFilters(bot_usernames=["harness-bot"]))
    assert result == []


def test_is_bot_comment_by_username() -> None:
    assert _is_bot_comment("harness-bot", "hello", ["harness-bot"]) is True


def test_is_bot_comment_by_prefix() -> None:
    assert _is_bot_comment("alice", "[harness] check done", ["harness-bot"]) is True


def test_is_bot_comment_normal_user() -> None:
    assert _is_bot_comment("alice", "looks good", ["harness-bot"]) is False


# ---------- _apply_filters — since_commit ----------


def test_filter_since_commit_excludes_older_comments() -> None:
    threads = [
        ReviewThread(
            thread_id="old",
            author="alice",
            path=None,
            line=None,
            body="old comment",
            posted_at="2026-04-05T00:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
        ),
        ReviewThread(
            thread_id="new",
            author="alice",
            path=None,
            line=None,
            body="new comment",
            posted_at="2026-04-08T00:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
        ),
    ]
    # Commit timestamp: 2026-04-07 — only the new thread should survive
    with patch(
        "darkfactory.utils.github.pr.comments._resolve_commit_timestamp",
        return_value="2026-04-07T00:00:00Z",
    ):
        result = _apply_filters(threads, CommentFilters(since_commit="abc123"))

    ids = {t.thread_id for t in result}
    assert "old" not in ids
    assert "new" in ids


# ---------- _apply_filters — single_comment_id ----------


def test_filter_single_comment_id_returns_one_thread() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(single_comment_id="comment-1"))
    assert len(result) == 1
    assert result[0].thread_id == "comment-1"


def test_filter_single_comment_id_no_match_returns_empty() -> None:
    threads = _parse_threads(FIXTURE_RAW)
    result = _apply_filters(threads, CommentFilters(single_comment_id="nonexistent"))
    assert result == []


# ---------- fetch_pr_comments integration ----------


def test_fetch_pr_comments_calls_gh_and_returns_threads() -> None:
    """fetch_pr_comments shells out to gh and returns filtered ReviewThread objects."""
    with patch(
        "darkfactory.utils.github.pr.comments._gh_fetch", return_value=FIXTURE_RAW
    ) as mock_fetch:
        result = fetch_pr_comments(42)

    mock_fetch.assert_called_once_with(42)
    assert isinstance(result, list)
    assert all(isinstance(t, ReviewThread) for t in result)
    # Resolved thread excluded by default
    ids = {t.thread_id for t in result}
    assert "rt-resolved" not in ids


def test_fetch_pr_comments_passes_filters_through() -> None:
    filters = CommentFilters(include_resolved=True)
    with patch(
        "darkfactory.utils.github.pr.comments._gh_fetch", return_value=FIXTURE_RAW
    ):
        result = fetch_pr_comments(42, filters=filters)

    ids = {t.thread_id for t in result}
    assert "rt-resolved" in ids


def test_fetch_pr_comments_empty_pr() -> None:
    with patch(
        "darkfactory.utils.github.pr.comments._gh_fetch",
        return_value={"reviewThreads": [], "reviews": [], "comments": []},
    ):
        result = fetch_pr_comments(99)
    assert result == []
