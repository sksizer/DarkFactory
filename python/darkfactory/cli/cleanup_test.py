"""Tests for cli.cleanup helpers."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.checks import StaleWorktree
from darkfactory.cli.cleanup import (
    _cleanup_all,
    _cleanup_merged,
    _cleanup_single,
    _find_orphaned_branch,
    _find_worktree_for_prd,
    _orphaned_branch_commit_count,
    _remove_worktree,
    cmd_cleanup,
)


# ---------- _remove_worktree ----------


def test_remove_worktree_calls_git_commands(tmp_path: Path) -> None:
    worktree = StaleWorktree(
        prd_id="PRD-1",
        branch="prd/PRD-1-my-feature",
        worktree_path=tmp_path / ".worktrees" / "PRD-1-my-feature",
        pr_state="MERGED",
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _remove_worktree(worktree, tmp_path)
    assert mock_run.call_count == 2
    first_call_args = mock_run.call_args_list[0][0][0]
    assert "worktree" in first_call_args
    assert "remove" in first_call_args
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "branch" in second_call_args
    assert "-D" in second_call_args


# ---------- _find_worktree_for_prd ----------


def test_find_worktree_for_prd_returns_none_when_no_worktrees_dir(
    tmp_path: Path,
) -> None:
    result = _find_worktree_for_prd("PRD-1", tmp_path)
    assert result is None


def test_find_worktree_for_prd_returns_none_when_not_found(tmp_path: Path) -> None:
    worktrees_dir = tmp_path / ".worktrees"
    worktrees_dir.mkdir()
    (worktrees_dir / "PRD-2-other").mkdir()
    with patch("darkfactory.checks._get_pr_state", return_value="MERGED"):
        result = _find_worktree_for_prd("PRD-1", tmp_path)
    assert result is None


def test_find_worktree_for_prd_finds_matching_entry(tmp_path: Path) -> None:
    worktrees_dir = tmp_path / ".worktrees"
    worktrees_dir.mkdir()
    prd_dir = worktrees_dir / "PRD-1-my-feature"
    prd_dir.mkdir()
    with patch("darkfactory.checks._get_pr_state", return_value="MERGED"):
        result = _find_worktree_for_prd("PRD-1", tmp_path)
    assert result is not None
    assert result.prd_id == "PRD-1"
    assert result.branch == "prd/PRD-1-my-feature"


# ---------- _find_orphaned_branch ----------


def test_find_orphaned_branch_returns_none_when_no_branch(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = _find_orphaned_branch("PRD-999", tmp_path)
    assert result is None


def test_find_orphaned_branch_returns_branch_name(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="  prd/PRD-999-some-feature\n"
        )
        result = _find_orphaned_branch("PRD-999", tmp_path)
    assert result == "prd/PRD-999-some-feature"


# ---------- _orphaned_branch_commit_count ----------


def test_orphaned_branch_commit_count_returns_zero_on_error(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _orphaned_branch_commit_count("prd/PRD-1-feat", tmp_path)
    assert result == 0


def test_orphaned_branch_commit_count_returns_count(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="3\n")
        result = _orphaned_branch_commit_count("prd/PRD-1-feat", tmp_path)
    assert result == 3


# ---------- _cleanup_single ----------


def test_cleanup_single_no_worktree_no_branch(tmp_path: Path) -> None:
    with (
        patch("darkfactory.cli.cleanup._find_worktree_for_prd", return_value=None),
        patch("darkfactory.cli.cleanup._find_orphaned_branch", return_value=None),
    ):
        result = _cleanup_single("PRD-1", False, tmp_path)
    assert result == 1


def test_cleanup_single_orphaned_branch_ahead_no_force(tmp_path: Path) -> None:
    with (
        patch("darkfactory.cli.cleanup._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli.cleanup._find_orphaned_branch",
            return_value="prd/PRD-1-feat",
        ),
        patch("darkfactory.cli.cleanup._orphaned_branch_commit_count", return_value=2),
    ):
        result = _cleanup_single("PRD-1", False, tmp_path)
    assert result == 1


def test_cleanup_single_orphaned_branch_force_deletes(tmp_path: Path) -> None:
    with (
        patch("darkfactory.cli.cleanup._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli.cleanup._find_orphaned_branch",
            return_value="prd/PRD-1-feat",
        ),
        patch("darkfactory.cli.cleanup._orphaned_branch_commit_count", return_value=2),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = _cleanup_single("PRD-1", True, tmp_path)
    assert result == 0


def test_cleanup_single_unsafe_worktree_returns_1(tmp_path: Path) -> None:
    worktree = StaleWorktree(
        prd_id="PRD-1",
        branch="prd/PRD-1-feat",
        worktree_path=tmp_path / ".worktrees" / "PRD-1-feat",
        pr_state="OPEN",
    )
    unsafe_status = MagicMock(safe=False, reason="PR is open")
    with (
        patch("darkfactory.cli.cleanup._find_worktree_for_prd", return_value=worktree),
        patch("darkfactory.cli.cleanup.is_safe_to_remove", return_value=unsafe_status),
    ):
        result = _cleanup_single("PRD-1", False, tmp_path)
    assert result == 1


def test_cleanup_single_safe_worktree_removes(tmp_path: Path) -> None:
    worktree = StaleWorktree(
        prd_id="PRD-1",
        branch="prd/PRD-1-feat",
        worktree_path=tmp_path / ".worktrees" / "PRD-1-feat",
        pr_state="MERGED",
    )
    safe_status = MagicMock(safe=True)
    with (
        patch("darkfactory.cli.cleanup._find_worktree_for_prd", return_value=worktree),
        patch("darkfactory.cli.cleanup.is_safe_to_remove", return_value=safe_status),
        patch("darkfactory.cli.cleanup._remove_worktree") as mock_remove,
    ):
        result = _cleanup_single("PRD-1", False, tmp_path)
    assert result == 0
    mock_remove.assert_called_once_with(worktree, tmp_path)


# ---------- _cleanup_merged ----------


def test_cleanup_merged_no_stale(tmp_path: Path) -> None:
    with patch("darkfactory.cli.cleanup.find_stale_worktrees", return_value=[]):
        result = _cleanup_merged(False, tmp_path)
    assert result == 0


def test_cleanup_merged_removes_safe_skips_unsafe(tmp_path: Path) -> None:
    safe_wt = StaleWorktree(
        prd_id="PRD-1",
        branch="prd/PRD-1-feat",
        worktree_path=tmp_path / "PRD-1-feat",
        pr_state="MERGED",
    )
    unsafe_wt = StaleWorktree(
        prd_id="PRD-2",
        branch="prd/PRD-2-feat",
        worktree_path=tmp_path / "PRD-2-feat",
        pr_state="OPEN",
    )
    safe_status = MagicMock(safe=True)
    unsafe_status = MagicMock(safe=False, reason="PR open")

    def fake_is_safe(wt: StaleWorktree, force: bool = False) -> MagicMock:
        return safe_status if wt.prd_id == "PRD-1" else unsafe_status

    with (
        patch(
            "darkfactory.cli.cleanup.find_stale_worktrees",
            return_value=[safe_wt, unsafe_wt],
        ),
        patch("darkfactory.cli.cleanup.is_safe_to_remove", side_effect=fake_is_safe),
        patch("darkfactory.cli.cleanup._remove_worktree") as mock_remove,
    ):
        result = _cleanup_merged(False, tmp_path)

    assert result == 1  # skipped > 0
    mock_remove.assert_called_once_with(safe_wt, tmp_path)


# ---------- _cleanup_all ----------


def test_cleanup_all_no_worktrees_dir(tmp_path: Path) -> None:
    result = _cleanup_all(False, tmp_path)
    assert result == 0


def test_cleanup_all_empty_worktrees_dir(tmp_path: Path) -> None:
    (tmp_path / ".worktrees").mkdir()
    result = _cleanup_all(False, tmp_path)
    assert result == 0


def test_cleanup_all_aborts_on_no_confirm(tmp_path: Path) -> None:
    worktrees_dir = tmp_path / ".worktrees"
    worktrees_dir.mkdir()
    (worktrees_dir / "PRD-1-feat").mkdir()
    with (
        patch("darkfactory.checks._get_pr_state", return_value="MERGED"),
        patch("builtins.input", return_value="n"),
    ):
        result = _cleanup_all(False, tmp_path)
    assert result == 1


def test_cleanup_all_removes_on_confirm(tmp_path: Path) -> None:
    worktrees_dir = tmp_path / ".worktrees"
    worktrees_dir.mkdir()
    (worktrees_dir / "PRD-1-feat").mkdir()
    safe_status = MagicMock(safe=True)
    with (
        patch("darkfactory.checks._get_pr_state", return_value="MERGED"),
        patch("builtins.input", return_value="y"),
        patch("darkfactory.cli.cleanup.is_safe_to_remove", return_value=safe_status),
        patch("darkfactory.cli.cleanup._remove_worktree") as mock_remove,
    ):
        result = _cleanup_all(False, tmp_path)
    assert result == 0
    assert mock_remove.call_count == 1


# ---------- cmd_cleanup ----------


def test_cmd_cleanup_no_args_returns_1(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id=None, merged=False, all_=False, force=False
    )
    with patch("darkfactory.cli.cleanup._find_repo_root", return_value=tmp_path):
        result = cmd_cleanup(args)
    assert result == 1


def test_cmd_cleanup_delegates_to_single(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id="PRD-1", merged=False, all_=False, force=False
    )
    with (
        patch("darkfactory.cli.cleanup._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.cleanup._cleanup_single", return_value=0) as mock_single,
    ):
        result = cmd_cleanup(args)
    assert result == 0
    mock_single.assert_called_once_with("PRD-1", False, tmp_path)


def test_cmd_cleanup_delegates_to_merged(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id=None, merged=True, all_=False, force=False
    )
    with (
        patch("darkfactory.cli.cleanup._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.cleanup._cleanup_merged", return_value=0) as mock_merged,
    ):
        result = cmd_cleanup(args)
    assert result == 0
    mock_merged.assert_called_once_with(False, tmp_path)


def test_cmd_cleanup_delegates_to_all(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id=None, merged=False, all_=True, force=False
    )
    with (
        patch("darkfactory.cli.cleanup._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.cleanup._cleanup_all", return_value=0) as mock_all,
    ):
        result = cmd_cleanup(args)
    assert result == 0
    mock_all.assert_called_once_with(False, tmp_path)
