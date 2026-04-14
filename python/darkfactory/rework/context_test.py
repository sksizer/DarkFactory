"""Tests for darkfactory.rework.context — shared rework discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.utils import Ok as _Ok
from darkfactory.utils.github import GhErr as _GhErr
from darkfactory.utils.github.pr.comments import CommentFilters, ReviewThread
from darkfactory.model import PRD
from darkfactory.rework.context import (
    ReworkContext,
    ReworkError,
    discover_rework_context,
    find_open_pr,
)


def _make_prd(prd_id: str = "PRD-001", slug: str = "my-feature") -> PRD:
    return PRD(
        id=prd_id,
        path=Path(f"/tmp/{prd_id}-{slug}.md"),
        slug=slug,
        title="Test PRD",
        kind="task",
        status="review",
        priority="medium",
        effort="m",
        capability="moderate",
        parent=None,
        depends_on=[],
        blocks=[],
        impacts=[],
        workflow=None,
        assignee=None,
        reviewers=[],
        target_version=None,
        created="2026-04-11",
        updated="2026-04-11",
        tags=[],
        raw_frontmatter={},
        body="",
    )


def _thread(thread_id: str = "t-1") -> ReviewThread:
    return ReviewThread(
        thread_id=thread_id,
        author="reviewer",
        path="src/foo.py",
        line=10,
        body="Please fix this.",
        posted_at="2026-04-10T00:00:00Z",
        is_resolved=False,
        replies=[],
        review_state=None,
    )


# ---------- find_open_pr ----------


def test_find_open_pr_returns_number_on_match(tmp_path: Path) -> None:
    with patch(
        "darkfactory.rework.context.gh_json", return_value=_Ok([{"number": 42}])
    ):
        assert find_open_pr("prd/PRD-001-my-feature", tmp_path) == 42


def test_find_open_pr_returns_none_when_no_prs(tmp_path: Path) -> None:
    with patch("darkfactory.rework.context.gh_json", return_value=_Ok([])):
        assert find_open_pr("prd/PRD-001-my-feature", tmp_path) is None


def test_find_open_pr_returns_none_on_gh_failure(tmp_path: Path) -> None:
    with patch(
        "darkfactory.rework.context.gh_json",
        return_value=_GhErr(1, "", "error", ["gh", "pr", "list"]),
    ):
        assert find_open_pr("prd/PRD-001-my-feature", tmp_path) is None


def test_find_open_pr_returns_none_on_missing_gh(tmp_path: Path) -> None:
    with patch(
        "darkfactory.rework.context.gh_json",
        return_value=_GhErr(-1, "", "FileNotFoundError", ["gh", "pr", "list"]),
    ):
        assert find_open_pr("prd/PRD-001-my-feature", tmp_path) is None


def test_find_open_pr_returns_none_on_invalid_json(tmp_path: Path) -> None:
    with patch(
        "darkfactory.rework.context.gh_json",
        return_value=_GhErr(
            -1, "NOT JSON", "invalid JSON in stdout", ["gh", "pr", "list"]
        ),
    ):
        assert find_open_pr("prd/PRD-001-my-feature", tmp_path) is None


# ---------- discover_rework_context ----------


def test_discover_raises_when_no_worktree(tmp_path: Path) -> None:
    prd = _make_prd()
    with patch("darkfactory.rework.context.find_worktree_for_prd", return_value=None):
        with pytest.raises(ReworkError, match="No worktree found"):
            discover_rework_context(
                prd,
                tmp_path,
                comment_filters=CommentFilters(),
                reply_to_comments=False,
            )


def test_discover_raises_when_no_open_pr(tmp_path: Path) -> None:
    prd = _make_prd()
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)
    with (
        patch(
            "darkfactory.rework.context.find_worktree_for_prd", return_value=worktree
        ),
        patch("darkfactory.rework.context.find_open_pr", return_value=None),
    ):
        with pytest.raises(ReworkError, match="No open PR found"):
            discover_rework_context(
                prd,
                tmp_path,
                comment_filters=CommentFilters(),
                reply_to_comments=False,
            )


def test_discover_raises_when_guard_blocked(tmp_path: Path) -> None:
    prd = _make_prd()
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)

    fake_guard = MagicMock()
    fake_guard.is_blocked.return_value = True
    fake_guard.get_consecutive_no_change.return_value = 3
    fake_guard.state_file = tmp_path / ".darkfactory" / "state" / "rework-guard.json"

    with (
        patch(
            "darkfactory.rework.context.find_worktree_for_prd", return_value=worktree
        ),
        patch("darkfactory.rework.context.find_open_pr", return_value=42),
        patch("darkfactory.rework.context.ReworkGuard", return_value=fake_guard),
    ):
        with pytest.raises(ReworkError, match="blocked by the rework loop guard"):
            discover_rework_context(
                prd,
                tmp_path,
                comment_filters=CommentFilters(),
                reply_to_comments=False,
            )


def test_discover_returns_context_with_threads(tmp_path: Path) -> None:
    prd = _make_prd()
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)
    threads = [_thread("t-1"), _thread("t-2")]

    fake_guard = MagicMock()
    fake_guard.is_blocked.return_value = False

    with (
        patch(
            "darkfactory.rework.context.find_worktree_for_prd", return_value=worktree
        ),
        patch("darkfactory.rework.context.find_open_pr", return_value=42),
        patch("darkfactory.rework.context.ReworkGuard", return_value=fake_guard),
        patch(
            "darkfactory.rework.context._fetch_pr_comments", return_value=threads
        ) as mock_fetch,
    ):
        filters = CommentFilters(include_resolved=True, reviewer="alice")
        ctx = discover_rework_context(
            prd,
            tmp_path,
            comment_filters=filters,
            reply_to_comments=True,
        )

    assert isinstance(ctx, ReworkContext)
    assert ctx.worktree_path == worktree
    assert ctx.pr_number == 42
    assert ctx.branch_name == "prd/PRD-001-my-feature"
    assert ctx.review_threads == threads
    assert ctx.comment_filters is filters
    assert ctx.reply_to_comments is True
    # Fetch was called with the full filter set — CLI args propagate.
    mock_fetch.assert_called_once_with(42, filters=filters)


def test_discover_skips_fetch_when_disabled(tmp_path: Path) -> None:
    prd = _make_prd()
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)

    fake_guard = MagicMock()
    fake_guard.is_blocked.return_value = False

    with (
        patch(
            "darkfactory.rework.context.find_worktree_for_prd", return_value=worktree
        ),
        patch("darkfactory.rework.context.find_open_pr", return_value=42),
        patch("darkfactory.rework.context.ReworkGuard", return_value=fake_guard),
        patch("darkfactory.rework.context._fetch_pr_comments") as mock_fetch,
    ):
        ctx = discover_rework_context(
            prd,
            tmp_path,
            comment_filters=CommentFilters(),
            reply_to_comments=False,
            fetch_comments=False,
        )

    assert ctx.review_threads == []
    mock_fetch.assert_not_called()
