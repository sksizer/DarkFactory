"""Unit tests for the set_status built-in."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.engine import PrdWorkflowRun
from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.set_status import set_status
from darkfactory.workflow import RunContext


def _make_set_status_ctx(
    *, dry_run: bool = False, worktree_path: Path | None = None
) -> RunContext:
    """Build a RunContext for set_status tests."""
    repo = Path("/repo")
    ctx = make_builtin_ctx(
        repo,
        dry_run=dry_run,
        prd_id="PRD-999",
        worktree_path=worktree_path,
        repo_root=repo,
    )
    # Override the PRD's status and path on the in-memory object
    prd_run = ctx.state.get(PrdWorkflowRun)
    prd_run.prd.status = "ready"
    prd_run.prd.path = repo / ".darkfactory" / "prds" / "PRD-999-test.md"
    return ctx


def test_dry_run_logs_and_does_not_call_set_status_at() -> None:
    ctx = _make_set_status_ctx(dry_run=True, worktree_path=Path("/worktrees/PRD-999"))

    with patch("darkfactory.operations.set_status.prd_module") as mock_prd:
        set_status(ctx, to="in-progress")

    mock_prd.set_status_at.assert_not_called()
    # dry-run path returns without error -- that's the contract


def test_missing_worktree_raises_runtime_error() -> None:
    ctx = _make_set_status_ctx(dry_run=False, worktree_path=None)

    with pytest.raises(RuntimeError, match="set_status requires a worktree"):
        set_status(ctx, to="in-progress")


def test_successful_update_calls_set_status_at_and_updates_ctx() -> None:
    worktree = Path("/worktrees/PRD-999")
    ctx = _make_set_status_ctx(dry_run=False, worktree_path=worktree)

    with patch("darkfactory.operations.set_status.prd_module") as mock_prd:
        set_status(ctx, to="done")

    expected_target = worktree / ".darkfactory" / "prds" / "PRD-999-test.md"
    mock_prd.set_status_at.assert_called_once_with(expected_target, "done")
    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.prd.status == "done"
    assert prd_run.prd.updated is not None
