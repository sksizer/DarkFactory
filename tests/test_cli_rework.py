"""Tests for `prd rework` CLI subcommand.

After the rework CLI/workflow consolidation (see ``rework_context.py``
and ``builtins/resolve_rework_context.py``), the CLI no longer
duplicates worktree/PR/comment discovery — it delegates everything to
:func:`~darkfactory.rework_context.discover_rework_context`. These
tests patch that single entry point rather than the former private
helpers (``find_worktree``, ``find_open_pr``, ``fetch_pr_comments``)
that used to live in ``cli/rework.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.cli import main
from darkfactory.pr_comments import CommentFilters, ReviewThread
from darkfactory.rework_context import ReworkContext, ReworkError

from .conftest import write_prd


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


def _base_args(prds_dir: Path) -> list[str]:
    return ["--prd-dir", str(prds_dir), "rework"]


def _make_discovered(
    tmp_path: Path,
    *,
    pr_number: int = 42,
    threads: list[ReviewThread] | None = None,
    reply_to_comments: bool = False,
) -> ReworkContext:
    worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    worktree.mkdir(parents=True, exist_ok=True)
    return ReworkContext(
        worktree_path=worktree,
        pr_number=pr_number,
        branch_name="prd/PRD-001-my-feature",
        review_threads=threads or [],
        comment_filters=CommentFilters(),
        reply_to_comments=reply_to_comments,
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


# ---------- status validation ----------


def test_rework_errors_if_prd_not_in_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="ready")

    with pytest.raises(SystemExit) as exc_info:
        main([*_base_args(prds_dir), "PRD-001"])

    assert exc_info.value.code != 0 or isinstance(exc_info.value.code, str)
    assert "ready" in str(exc_info.value.code)
    assert "review" in str(exc_info.value.code)


# ---------- discovery errors ----------


def test_rework_errors_when_discovery_reports_missing_worktree(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    with patch(
        "darkfactory.cli.rework.discover_rework_context",
        side_effect=ReworkError("No worktree found for PRD-001. Run ..."),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([*_base_args(prds_dir), "PRD-001"])

    assert "No worktree found" in str(exc_info.value.code)


def test_rework_errors_when_discovery_reports_no_open_pr(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    with patch(
        "darkfactory.cli.rework.discover_rework_context",
        side_effect=ReworkError("No open PR found for PRD-001"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([*_base_args(prds_dir), "PRD-001"])

    assert "No open PR found" in str(exc_info.value.code)


def test_rework_errors_when_discovery_reports_guard_blocked(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    with patch(
        "darkfactory.cli.rework.discover_rework_context",
        side_effect=ReworkError(
            "PRD-001 is blocked by the rework loop guard after 2 cycles"
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([*_base_args(prds_dir), "PRD-001", "--execute"])

    assert "blocked by the rework loop guard" in str(exc_info.value.code)


# ---------- dry-run output ----------


def test_rework_dry_run_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    discovered = _make_discovered(tmp_path, threads=[_thread()])

    with patch(
        "darkfactory.cli.rework.discover_rework_context", return_value=discovered
    ):
        result = main([*_base_args(prds_dir), "PRD-001"])

    assert result == 0
    out = capsys.readouterr().out
    assert "Would rework PRD-001" in out
    assert str(discovered.worktree_path) in out
    assert "#42" in out
    assert "prd/PRD-001-my-feature" in out
    assert "Comments: 1" in out


def test_rework_dry_run_passes_filter_flags_to_discovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Filter CLI args reach discover_rework_context in the CommentFilters."""
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    discovered = _make_discovered(tmp_path)

    with patch(
        "darkfactory.cli.rework.discover_rework_context", return_value=discovered
    ) as mock_discover:
        main(
            [
                *_base_args(prds_dir),
                "PRD-001",
                "--all",
                "--reviewer",
                "alice",
                "--since",
                "abc123",
            ]
        )

    _, kwargs = mock_discover.call_args
    filters = kwargs["comment_filters"]
    assert filters.include_resolved is True
    assert filters.reviewer == "alice"
    assert filters.since_commit == "abc123"


# ---------- --execute flag ----------


def test_rework_execute_no_comments_exits_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When discovery reports no unaddressed comments, exit 0 without running."""
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    discovered = _make_discovered(tmp_path, threads=[])

    with (
        patch(
            "darkfactory.cli.rework.discover_rework_context", return_value=discovered
        ),
        patch("darkfactory.cli.rework.run_workflow") as mock_run,
    ):
        result = main([*_base_args(prds_dir), "PRD-001", "--execute"])

    assert result == 0
    out = capsys.readouterr().out
    assert "Would rework" not in out
    assert "No unaddressed comments" in out
    mock_run.assert_not_called()


def test_rework_execute_with_comments_invokes_workflow(
    tmp_path: Path,
) -> None:
    """When comments exist, invoke run_workflow with pre-discovered state."""
    from darkfactory.runner import RunResult
    from darkfactory.workflow import Workflow

    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    thread = _thread()
    discovered = _make_discovered(tmp_path, threads=[thread], reply_to_comments=True)

    fake_rework_wf = Workflow(name="rework", tasks=[])

    with (
        patch(
            "darkfactory.cli.rework.discover_rework_context", return_value=discovered
        ),
        patch(
            "darkfactory.cli.rework.load_workflows",
            return_value={"rework": fake_rework_wf},
        ),
        patch(
            "darkfactory.cli.rework.run_workflow",
            return_value=RunResult(success=True),
        ) as mock_run,
    ):
        result = main(
            [*_base_args(prds_dir), "PRD-001", "--execute", "--reply-to-comments"]
        )

    assert result == 0
    assert mock_run.called
    # The CLI hands the discovered state over via context_overrides so the
    # resolve_rework_context builtin is a no-op when the workflow starts.
    _, kwargs = mock_run.call_args
    assert kwargs["dry_run"] is False
    overrides = kwargs["context_overrides"]
    assert overrides["worktree_path"] == discovered.worktree_path
    assert overrides["cwd"] == discovered.worktree_path
    assert overrides["pr_number"] == 42
    assert overrides["review_threads"] == [thread]
    assert overrides["reply_to_comments"] is True
    assert isinstance(overrides["comment_filters"], CommentFilters)
