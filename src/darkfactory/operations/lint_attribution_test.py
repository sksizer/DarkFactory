"""Unit tests for lint_attribution builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.engine import PrdWorkflowRun
from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.lint_attribution import lint_attribution
from darkfactory.workflow import RunContext


def _make_lint_ctx(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    run_summary: str | None = None,
    branch_name: str = "prd/PRD-001-test",
    base_ref: str = "main",
) -> RunContext:
    """Build a RunContext for lint_attribution tests."""
    ctx = make_builtin_ctx(
        tmp_path,
        dry_run=dry_run,
        branch_name=branch_name,
        base_ref=base_ref,
    )
    # Replace PrdWorkflowRun with updated run_summary if needed.
    if run_summary is not None:
        prd_run = ctx.state.get(PrdWorkflowRun)
        ctx.state.put(
            PrdWorkflowRun(
                prd=prd_run.prd,
                workflow=prd_run.workflow,
                run_summary=run_summary,
            )
        )
    return ctx


# ---------- dry-run path ----------


def test_dry_run_logs_and_returns(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        lint_attribution(ctx)
    mock_run.assert_not_called()


# ---------- clean commits pass ----------


def test_clean_commits_pass(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(tmp_path, dry_run=False, run_summary="All good")
    clean_git_output = "abc123\x00Fix a bug\x1e"
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            [], returncode=0, stdout=clean_git_output, stderr=""
        )
        lint_attribution(ctx)


def test_clean_no_commits(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(tmp_path, dry_run=False)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        )
        lint_attribution(ctx)


# ---------- forbidden pattern in commit message ----------


def test_commit_message_violation_raises(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(tmp_path, dry_run=False)
    bad_commit_output = (
        "deadbeef1234\x00Fix thing\n\nCo-Authored-By: Claude <claude@anthropic.com>\x1e"
    )
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            [], returncode=0, stdout=bad_commit_output, stderr=""
        )
        with pytest.raises(RuntimeError, match="forbidden attribution"):
            lint_attribution(ctx)


def test_generated_with_claude_code_raises(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(tmp_path, dry_run=False)
    bad_commit_output = (
        "deadbeef1234\x00Fix thing\n\n\U0001f916 Generated with Claude Code\x1e"
    )
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            [], returncode=0, stdout=bad_commit_output, stderr=""
        )
        with pytest.raises(RuntimeError, match="forbidden attribution"):
            lint_attribution(ctx)


# ---------- forbidden pattern in run_summary ----------


def test_run_summary_violation_raises(tmp_path: Path) -> None:
    ctx = _make_lint_ctx(
        tmp_path,
        dry_run=False,
        run_summary="Generated with Claude Code",
    )
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        )
        with pytest.raises(RuntimeError, match="forbidden attribution"):
            lint_attribution(ctx)
