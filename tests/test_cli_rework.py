"""Tests for `prd rework` CLI subcommand."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.cli import main

from .conftest import write_prd


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


def _base_args(prds_dir: Path) -> list[str]:
    return ["--prd-dir", str(prds_dir), "rework"]


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
    # SystemExit with a string message indicates an error
    assert "ready" in str(exc_info.value.code)
    assert "review" in str(exc_info.value.code)


# ---------- worktree validation ----------


def test_rework_errors_if_no_worktree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    # Simulate git worktree list returning no matching worktree
    with patch("darkfactory.cli.rework.find_worktree", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            main([*_base_args(prds_dir), "PRD-001"])

    assert "No worktree found" in str(exc_info.value.code)


# ---------- PR validation ----------


def test_rework_errors_if_no_open_pr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    fake_worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    fake_worktree.mkdir(parents=True)

    with (
        patch("darkfactory.cli.rework.find_worktree", return_value=fake_worktree),
        patch("darkfactory.cli.rework.find_open_pr", return_value=None),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main([*_base_args(prds_dir), "PRD-001"])

    assert "No open PR found" in str(exc_info.value.code)


# ---------- dry-run output ----------


def test_rework_dry_run_prints_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    fake_worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    fake_worktree.mkdir(parents=True)

    with (
        patch("darkfactory.cli.rework.find_worktree", return_value=fake_worktree),
        patch("darkfactory.cli.rework.find_open_pr", return_value=42),
    ):
        result = main([*_base_args(prds_dir), "PRD-001"])

    assert result == 0
    out = capsys.readouterr().out
    assert "Would rework PRD-001" in out
    assert str(fake_worktree) in out
    assert "#42" in out
    assert "prd/PRD-001-my-feature" in out


# ---------- --execute flag ----------


def test_rework_execute_no_comments_exits_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When no unaddressed comments exist, exit 0 with an informational message."""
    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    fake_worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    fake_worktree.mkdir(parents=True)

    with (
        patch("darkfactory.cli.rework.find_worktree", return_value=fake_worktree),
        patch("darkfactory.cli.rework.find_open_pr", return_value=42),
        patch("darkfactory.cli.rework.fetch_pr_comments", return_value=[]),
    ):
        result = main([*_base_args(prds_dir), "PRD-001", "--execute"])

    assert result == 0
    # Dry-run output should NOT appear when --execute is passed
    out = capsys.readouterr().out
    assert "Would rework" not in out
    assert "No unaddressed comments" in out


def test_rework_execute_with_comments_invokes_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When comments exist, load the rework workflow and invoke the runner."""
    from darkfactory.pr_comments import ReviewThread
    from darkfactory.runner import RunResult
    from darkfactory.workflow import Workflow

    _init_git_repo(tmp_path)
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")

    fake_worktree = tmp_path / ".worktrees" / "PRD-001-my-feature"
    fake_worktree.mkdir(parents=True)

    fake_rework_wf = Workflow(name="rework", tasks=[])
    thread = ReviewThread(
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

    with (
        patch("darkfactory.cli.rework.find_worktree", return_value=fake_worktree),
        patch("darkfactory.cli.rework.find_open_pr", return_value=42),
        patch("darkfactory.cli.rework.fetch_pr_comments", return_value=[thread]),
        patch("darkfactory.cli.rework.load_workflows", return_value={"rework": fake_rework_wf}),
        patch("darkfactory.cli.rework.run_workflow", return_value=RunResult(success=True)) as mock_run,
    ):
        result = main([*_base_args(prds_dir), "PRD-001", "--execute"])

    assert result == 0
    assert mock_run.called
    # Verify the runner was called with rework-specific kwargs
    _, kwargs = mock_run.call_args
    assert kwargs["initial_worktree_path"] == fake_worktree
    assert kwargs["initial_pr_number"] == 42
    assert kwargs["initial_review_threads"] == [thread]
    assert kwargs["dry_run"] is False
