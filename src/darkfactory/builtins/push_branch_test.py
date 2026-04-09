"""Unit tests for push_branch builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.builtins.push_branch import push_branch


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    """Build a minimal ExecutionContext mock for push_branch tests."""
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.cwd = tmp_path
    ctx.branch_name = "prd/PRD-001-test-thing"
    return ctx


# ---------- dry-run path ----------


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    push_branch(ctx)
    ctx.logger.info.assert_called()
    call_args = ctx.logger.info.call_args[0]
    assert "[dry-run]" in call_args[0]
    assert "git" in str(call_args)
    assert "push" in str(call_args)


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.builtins.push_branch.subprocess.run") as mock_run:
        push_branch(ctx)
    mock_run.assert_not_called()


# ---------- successful push ----------


def test_successful_push_calls_git_push(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch("darkfactory.builtins.push_branch.subprocess.run") as mock_run:
        push_branch(ctx)

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args == ["git", "push", "-u", "origin", "prd/PRD-001-test-thing"]


def test_successful_push_with_correct_cwd(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch("darkfactory.builtins.push_branch.subprocess.run") as mock_run:
        push_branch(ctx)

    # Verify cwd is passed correctly
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)
    assert call_kwargs["check"] is True
    assert call_kwargs["capture_output"] is True
    assert call_kwargs["text"] is True
