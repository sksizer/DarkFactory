"""Tests for the resolve_rework_context builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins.resolve_rework_context import resolve_rework_context
from darkfactory.pr_comments import CommentFilters, ReviewThread
from darkfactory.prd import PRD
from darkfactory.rework_context import ReworkContext, ReworkError
from darkfactory.workflow import ExecutionContext, Workflow


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


def _thread() -> ReviewThread:
    return ReviewThread(
        thread_id="t-1",
        author="reviewer",
        path="src/foo.py",
        line=10,
        body="Please fix this.",
        posted_at="2026-04-10T00:00:00Z",
        is_resolved=False,
        replies=[],
        review_state=None,
    )


def _make_ctx(
    tmp_path: Path,
    *,
    worktree_path: Path | None = None,
    review_threads: list[ReviewThread] | None = None,
    comment_filters: CommentFilters | None = None,
    reply_to_comments: bool = False,
    dry_run: bool = False,
) -> ExecutionContext:
    return ExecutionContext(
        prd=_make_prd(),
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        worktree_path=worktree_path,
        review_threads=review_threads,
        comment_filters=comment_filters,
        reply_to_comments=reply_to_comments,
        dry_run=dry_run,
    )


def test_noop_when_context_already_populated(tmp_path: Path) -> None:
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)
    ctx = _make_ctx(tmp_path, worktree_path=worktree, review_threads=[_thread()])

    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context"
    ) as mock_discover:
        resolve_rework_context(ctx)
        mock_discover.assert_not_called()

    # Nothing changes — the builtin trusted the pre-populated state.
    assert ctx.worktree_path == worktree
    assert ctx.review_threads == [_thread()]


def test_dry_run_sets_empty_threads_and_skips_discovery(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)

    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context"
    ) as mock_discover:
        resolve_rework_context(ctx)
        mock_discover.assert_not_called()

    assert ctx.review_threads == []


def test_calls_discover_when_ctx_empty(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)
    threads = [_thread()]
    discovered = ReworkContext(
        worktree_path=worktree,
        pr_number=42,
        branch_name="prd/PRD-001-my-feature",
        review_threads=threads,
        comment_filters=CommentFilters(),
        reply_to_comments=False,
    )

    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context",
        return_value=discovered,
    ) as mock_discover:
        resolve_rework_context(ctx)

    assert mock_discover.called
    # comment_filters defaults to an empty CommentFilters when unset on ctx.
    _, kwargs = mock_discover.call_args
    assert isinstance(kwargs["comment_filters"], CommentFilters)
    assert kwargs["reply_to_comments"] is False

    assert ctx.worktree_path == worktree
    assert ctx.cwd == worktree
    assert ctx.pr_number == 42
    assert ctx.review_threads == threads


def test_uses_ctx_filters_when_set(tmp_path: Path) -> None:
    filters = CommentFilters(include_resolved=True, reviewer="alice")
    ctx = _make_ctx(tmp_path, comment_filters=filters, reply_to_comments=True)
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)

    discovered = ReworkContext(
        worktree_path=worktree,
        pr_number=42,
        branch_name="prd/PRD-001-my-feature",
        review_threads=[],
        comment_filters=filters,
        reply_to_comments=True,
    )
    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context",
        return_value=discovered,
    ) as mock_discover:
        resolve_rework_context(ctx)

    _, kwargs = mock_discover.call_args
    assert kwargs["comment_filters"] is filters
    assert kwargs["reply_to_comments"] is True


def test_wraps_rework_error_as_runtime_error(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context",
        side_effect=ReworkError("No worktree found for PRD-001"),
    ):
        with pytest.raises(RuntimeError, match="No worktree found"):
            resolve_rework_context(ctx)


def test_emits_builtin_effect(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True)
    discovered = ReworkContext(
        worktree_path=worktree,
        pr_number=42,
        branch_name="prd/PRD-001-my-feature",
        review_threads=[_thread()],
        comment_filters=CommentFilters(),
        reply_to_comments=False,
    )

    fake_writer = MagicMock()
    ctx.event_writer = fake_writer

    with patch(
        "darkfactory.builtins.resolve_rework_context.discover_rework_context",
        return_value=discovered,
    ):
        resolve_rework_context(ctx)

    # At least one emit for the builtin_effect event.
    assert fake_writer.emit.called
    args, kwargs = fake_writer.emit.call_args
    assert args[0] == "task"
    assert args[1] == "builtin_effect"
    assert kwargs["task"] == "resolve_rework_context"
    assert kwargs["effect"] == "resolve"
