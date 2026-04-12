"""Unit tests for cleanup_worktree builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.cleanup_worktree import cleanup_worktree


# ---------- no worktree path set ----------


def test_no_worktree_path_logs_and_returns(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = None
    cleanup_worktree(ctx)
    ctx.logger.info.assert_called_once()
    assert "no worktree path" in ctx.logger.info.call_args[0][0]


def test_no_worktree_path_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = None
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- worktree already gone ----------


def test_worktree_already_gone_logs_and_returns(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = tmp_path / "nonexistent-worktree"
    cleanup_worktree(ctx)
    ctx.logger.info.assert_called_once()
    assert "already gone" in ctx.logger.info.call_args[0][0]


def test_worktree_already_gone_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = tmp_path / "nonexistent-worktree"
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- dry-run ----------


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.worktree_path = tmp_path / "my-worktree"
    ctx.worktree_path.mkdir()
    cleanup_worktree(ctx)
    ctx.logger.info.assert_called_once()
    logged = ctx.logger.info.call_args[0]
    assert "[dry-run]" in logged[0]


def test_dry_run_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.worktree_path = tmp_path / "my-worktree"
    ctx.worktree_path.mkdir()
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        cleanup_worktree(ctx)
    mock_run.assert_not_called()


# ---------- successful removal ----------


def test_successful_removal_calls_git_worktree_remove(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = tmp_path / "my-worktree"
    ctx.worktree_path.mkdir()

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
    assert str(ctx.worktree_path) in cmd


def test_successful_removal_passes_repo_root(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.worktree_path = tmp_path / "my-worktree"
    ctx.worktree_path.mkdir()

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        cleanup_worktree(ctx)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)
