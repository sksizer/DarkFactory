"""Unit tests for push_branch builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.push_branch import push_branch

_BRANCH = "prd/PRD-001-test-thing"


# ---------- dry-run path ----------


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True, branch_name=_BRANCH)
    # Should not raise — the builtin logs the dry-run message and returns
    push_branch(ctx)


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True, branch_name=_BRANCH)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        push_branch(ctx)
    mock_run.assert_not_called()


# ---------- successful push ----------


def test_successful_push_calls_git_push(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False, branch_name=_BRANCH)
    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        push_branch(ctx)

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args == ["git", "push", "-u", "origin", _BRANCH]


def test_successful_push_with_correct_cwd(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False, branch_name=_BRANCH)
    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        push_branch(ctx)

    # Verify cwd is passed correctly
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)
    assert call_kwargs["capture_output"] is True
    assert call_kwargs["text"] is True
