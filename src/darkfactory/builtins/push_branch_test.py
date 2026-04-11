"""Unit tests for push_branch builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.push_branch import push_branch

_BRANCH = "prd/PRD-001-test-thing"


# ---------- dry-run path ----------


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.branch_name = _BRANCH
    push_branch(ctx)
    ctx.logger.info.assert_called()
    call_args = ctx.logger.info.call_args[0]
    assert "[dry-run]" in call_args[0]
    assert "git" in str(call_args)
    assert "push" in str(call_args)


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.branch_name = _BRANCH
    with patch("darkfactory.git_ops.subprocess.run") as mock_run:
        push_branch(ctx)
    mock_run.assert_not_called()


# ---------- successful push ----------


def test_successful_push_calls_git_push(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False)
    ctx.branch_name = _BRANCH
    with patch("darkfactory.git_ops.subprocess.run") as mock_run:
        push_branch(ctx)

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args == ["git", "push", "-u", "origin", _BRANCH]


def test_successful_push_with_correct_cwd(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False)
    ctx.branch_name = _BRANCH
    with patch("darkfactory.git_ops.subprocess.run") as mock_run:
        push_branch(ctx)

    # Verify cwd is passed correctly
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)
    assert call_kwargs["check"] is True
    assert call_kwargs["capture_output"] is True
    assert call_kwargs["text"] is True
