"""Unit tests for ensure_worktree builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.ensure_worktree import (
    _branch_exists_local,
    _branch_exists_remote,
    _worktree_target,
    ensure_worktree,
)


# ---------- helpers ----------


def _make_ensure_worktree_ctx(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    """Build a minimal ExecutionContext mock for ensure_worktree tests."""
    ctx = make_builtin_ctx(tmp_path, dry_run=dry_run)
    ctx.prd.slug = "test-thing"
    ctx.branch_name = "prd/PRD-001-test-thing"
    ctx.base_ref = "main"
    ctx._worktree_lock = None
    return ctx


# ---------- _worktree_target ----------


def test_worktree_target_builds_path(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)
    result = _worktree_target(ctx)
    assert result == tmp_path / ".worktrees" / "PRD-001-test-thing"


# ---------- dry-run path ----------


def test_dry_run_sets_worktree_path_and_cwd(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path, dry_run=True)
    ensure_worktree(ctx)
    expected = tmp_path / ".worktrees" / "PRD-001-test-thing"
    assert ctx.worktree_path == expected
    assert ctx.cwd == expected


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        ensure_worktree(ctx)
    mock_run.assert_not_called()


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path, dry_run=True)
    ensure_worktree(ctx)
    ctx.logger.info.assert_called()


# ---------- resume existing worktree ----------


def test_resume_existing_worktree(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)
    worktree_path = tmp_path / ".worktrees" / "PRD-001-test-thing"
    worktree_path.mkdir(parents=True)

    resume_status = MagicMock()
    resume_status.safe = True

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree.is_resume_safe",
            return_value=resume_status,
        ),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        ensure_worktree(ctx)

    assert ctx.worktree_path == worktree_path
    assert ctx.cwd == worktree_path


def test_resume_unsafe_raises(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)
    worktree_path = tmp_path / ".worktrees" / "PRD-001-test-thing"
    worktree_path.mkdir(parents=True)

    resume_status = MagicMock()
    resume_status.safe = False
    resume_status.reason = "branch diverged from main"

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree.is_resume_safe",
            return_value=resume_status,
        ),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        with pytest.raises(RuntimeError, match="branch diverged from main"):
            ensure_worktree(ctx)

    mock_lock.release.assert_called_once()


# ---------- branch-exists error ----------


def test_branch_exists_local_raises(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_local",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        with pytest.raises(RuntimeError, match="already exists but worktree"):
            ensure_worktree(ctx)

    mock_lock.release.assert_called_once()


def test_branch_exists_remote_raises(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_local",
            return_value=False,
        ),
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=True,
        ),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        with pytest.raises(RuntimeError, match="already exists but worktree"):
            ensure_worktree(ctx)

    mock_lock.release.assert_called_once()


# ---------- successful creation ----------


def test_successful_creation_calls_git_worktree_add(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_local",
            return_value=False,
        ),
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ),
        patch("darkfactory.utils.git._ops.subprocess.run") as mock_run,
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        ensure_worktree(ctx)

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "worktree" in call_args
    assert "add" in call_args
    assert "-b" in call_args
    assert ctx.branch_name in call_args


def test_successful_creation_sets_ctx(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)
    expected = tmp_path / ".worktrees" / "PRD-001-test-thing"

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_local",
            return_value=False,
        ),
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ),
        patch("darkfactory.utils.git._ops.subprocess.run"),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        ensure_worktree(ctx)

    assert ctx.worktree_path == expected
    assert ctx.cwd == expected


# ---------- lock acquisition and timeout ----------


def test_lock_acquired_on_success(tmp_path: Path) -> None:
    ctx = _make_ensure_worktree_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_local",
            return_value=False,
        ),
        patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ),
        patch("darkfactory.utils.git._ops.subprocess.run"),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        ensure_worktree(ctx)

    mock_lock.acquire.assert_called_once_with(timeout=0)
    assert ctx._worktree_lock is mock_lock


def test_lock_timeout_raises_runtime_error(tmp_path: Path) -> None:
    from filelock import Timeout

    ctx = _make_ensure_worktree_ctx(tmp_path)

    with patch("darkfactory.builtins.ensure_worktree.FileLock") as mock_lock_cls:
        mock_lock = MagicMock()
        mock_lock.acquire.side_effect = Timeout("test.lock")
        mock_lock_cls.return_value = mock_lock

        with pytest.raises(RuntimeError, match="already being worked on"):
            ensure_worktree(ctx)


# ---------- _branch_exists_local ----------


def test_branch_exists_local_true_on_zero_returncode() -> None:
    import subprocess

    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        assert _branch_exists_local(Path("/repo"), "my-branch") is True


def test_branch_exists_local_false_on_nonzero_returncode() -> None:
    import subprocess

    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=1)
        assert _branch_exists_local(Path("/repo"), "my-branch") is False


# ---------- _branch_exists_remote ----------


def test_branch_exists_remote_true_on_zero_returncode() -> None:
    import subprocess

    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=0)
        assert _branch_exists_remote(Path("/repo"), "my-branch") is True


def test_branch_exists_remote_false_on_timeout() -> None:
    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        mock_run.side_effect = __import__("subprocess").TimeoutExpired(
            cmd=["git"], timeout=10
        )
        assert _branch_exists_remote(Path("/repo"), "my-branch") is False


def test_branch_exists_remote_false_on_exception() -> None:
    with patch("darkfactory.utils.git._ops.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("network error")
        assert _branch_exists_remote(Path("/repo"), "my-branch") is False
