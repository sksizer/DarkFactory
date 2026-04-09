"""Unit tests for the set_status built-in."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins.set_status import set_status


def _make_ctx(*, dry_run: bool = False, worktree_path: Path | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.worktree_path = worktree_path
    ctx.prd.id = "PRD-999"
    ctx.prd.status = "ready"
    ctx.prd.path = Path("/repo/.darkfactory/prds/PRD-999-test.md")
    ctx.repo_root = Path("/repo")
    return ctx


def test_dry_run_logs_and_does_not_call_set_status_at() -> None:
    ctx = _make_ctx(dry_run=True, worktree_path=Path("/worktrees/PRD-999"))

    with patch("darkfactory.builtins.set_status.prd_module") as mock_prd:
        set_status(ctx, to="in-progress")

    mock_prd.set_status_at.assert_not_called()
    ctx.logger.info.assert_called_once()
    call_args = ctx.logger.info.call_args[0]
    assert "dry-run" in call_args[0]


def test_missing_worktree_raises_runtime_error() -> None:
    ctx = _make_ctx(dry_run=False, worktree_path=None)

    with pytest.raises(RuntimeError, match="set_status requires a worktree"):
        set_status(ctx, to="in-progress")


def test_successful_update_calls_set_status_at_and_updates_ctx() -> None:
    worktree = Path("/worktrees/PRD-999")
    ctx = _make_ctx(dry_run=False, worktree_path=worktree)
    ctx.prd.path = Path("/repo/.darkfactory/prds/PRD-999-test.md")
    ctx.repo_root = Path("/repo")

    with patch("darkfactory.builtins.set_status.prd_module") as mock_prd:
        set_status(ctx, to="done")

    expected_target = worktree / ".darkfactory" / "prds" / "PRD-999-test.md"
    mock_prd.set_status_at.assert_called_once_with(expected_target, "done")
    assert ctx.prd.status == "done"
    assert ctx.prd.updated is not None
