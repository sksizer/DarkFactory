"""Unit tests for cleanup_worktree builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.cleanup_worktree import cleanup_worktree


# ---------- no worktree path set ----------


def test_no_worktree_path_logs_and_returns(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, worktree_path=None)
    # Should not raise — the builtin logs and returns when no worktree is set
    cleanup_worktree(ctx)


def test_no_worktree_path_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, worktree_path=None)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- worktree already gone ----------


def test_worktree_already_gone_logs_and_returns(tmp_path: Path) -> None:
    gone = tmp_path / "nonexistent-worktree"
    ctx = make_builtin_ctx(tmp_path, worktree_path=gone)
    # Should not raise — the builtin logs and returns when the dir is gone
    cleanup_worktree(ctx)


def test_worktree_already_gone_no_subprocess(tmp_path: Path) -> None:
    gone = tmp_path / "nonexistent-worktree"
    ctx = make_builtin_ctx(tmp_path, worktree_path=gone)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- dry-run ----------


def test_dry_run_logs_command(tmp_path: Path) -> None:
    wt = tmp_path / "my-worktree"
    wt.mkdir()
    ctx = make_builtin_ctx(tmp_path, dry_run=True, worktree_path=wt)
    # Should not raise — the builtin logs the dry-run message and returns
    cleanup_worktree(ctx)


def test_dry_run_no_subprocess(tmp_path: Path) -> None:
    wt = tmp_path / "my-worktree"
    wt.mkdir()
    ctx = make_builtin_ctx(tmp_path, dry_run=True, worktree_path=wt)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- successful removal ----------


def test_successful_removal_calls_git_worktree_remove(tmp_path: Path) -> None:
    wt = tmp_path / "my-worktree"
    wt.mkdir()
    ctx = make_builtin_ctx(tmp_path, worktree_path=wt)

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        cleanup_worktree(ctx)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "git" in cmd
    assert "worktree" in cmd
    assert "remove" in cmd
    assert str(wt) in cmd


def test_successful_removal_passes_repo_root(tmp_path: Path) -> None:
    wt = tmp_path / "my-worktree"
    wt.mkdir()
    ctx = make_builtin_ctx(tmp_path, worktree_path=wt)

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        cleanup_worktree(ctx)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)
