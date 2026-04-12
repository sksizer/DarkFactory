"""Tests for the fetch_pr_comments builtin.

The rework workflow itself no longer references this builtin directly
— ``resolve_rework_context`` subsumes the discovery flow. The builtin
is kept as a standalone primitive for any future workflow that only
needs to fetch PR threads without the worktree/guard checks.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.builtins.fetch_pr_comments import fetch_pr_comments as builtin_fn
from darkfactory.engine import ReworkState
from darkfactory.utils.github.pr.comments import ReviewThread
from darkfactory.model import PRD
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
    pr_number: int | None = None,
    review_threads: list[ReviewThread] | None = None,
    dry_run: bool = False,
) -> ExecutionContext:
    ctx = ExecutionContext(
        prd=_make_prd(),
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        dry_run=dry_run,
    )
    ctx.state.put(
        ReworkState(
            pr_number=pr_number,
            review_threads=review_threads,
        )
    )
    return ctx


def test_noop_when_preloaded(tmp_path: Path) -> None:
    """No-op when ``ctx.review_threads`` is already populated."""
    threads = [_thread()]
    ctx = _make_ctx(tmp_path, review_threads=threads)

    with patch("darkfactory.utils.github.pr.comments.fetch_pr_comments") as mock_fetch:
        builtin_fn(ctx)
        mock_fetch.assert_not_called()

    assert ctx.state.get(ReworkState).review_threads is threads


def test_dry_run_sets_empty_threads(tmp_path: Path) -> None:
    """In dry-run, ``review_threads`` is set to ``[]`` without calling gh."""
    ctx = _make_ctx(tmp_path, pr_number=42, dry_run=True)
    builtin_fn(ctx)
    assert ctx.state.get(ReworkState).review_threads == []


def test_fetches_when_pr_number_set(tmp_path: Path) -> None:
    """When ``pr_number`` is set and threads not preloaded, fetch via gh."""
    ctx = _make_ctx(tmp_path, pr_number=42)

    fetched = [_thread()]
    with patch(
        "darkfactory.utils.github.pr.comments.fetch_pr_comments", return_value=fetched
    ) as mock_fetch:
        builtin_fn(ctx)
        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args.args[0] == 42

    assert ctx.state.get(ReworkState).review_threads == fetched


def test_raises_without_pr_number(tmp_path: Path) -> None:
    """Without ``pr_number`` or pre-loaded threads in live mode, raise."""
    ctx = _make_ctx(tmp_path)
    with pytest.raises(RuntimeError, match="pr_number must be set"):
        builtin_fn(ctx)
