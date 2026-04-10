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


def test_rework_execute_exits_cleanly(
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
        result = main([*_base_args(prds_dir), "PRD-001", "--execute"])

    assert result == 0
    # Dry-run output should NOT appear when --execute is passed
    out = capsys.readouterr().out
    assert "Would rework" not in out
