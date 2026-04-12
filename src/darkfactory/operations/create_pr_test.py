"""Unit tests for create_pr builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.operations.create_pr import (
    _extract_acceptance_criteria,
    _pr_body,
    create_pr,
)
from darkfactory.utils import Ok


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    """Build a minimal ExecutionContext mock for create_pr tests."""
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.cwd = tmp_path
    ctx.base_ref = "main"
    ctx.run_summary = None
    ctx.prd.id = "PRD-001"
    ctx.prd.title = "Test PR"
    ctx.prd.path = tmp_path / ".darkfactory" / "prds" / "PRD-001.md"
    ctx.prd.body = ""
    ctx.repo_root = tmp_path
    ctx.workflow.name = "test-workflow"
    return ctx


# ---------- _extract_acceptance_criteria ----------


def test_extract_acceptance_criteria_basic() -> None:
    body = """
## Acceptance Criteria

- [ ] AC-1: First criterion
- [ ] AC-2: Second criterion
- [x] AC-3: Already done
"""
    result = _extract_acceptance_criteria(body)
    assert result == ["AC-1: First criterion", "AC-2: Second criterion"]


def test_extract_acceptance_criteria_empty() -> None:
    assert _extract_acceptance_criteria("") == []


def test_extract_acceptance_criteria_no_acs() -> None:
    assert _extract_acceptance_criteria("No acceptance criteria here.") == []


def test_extract_acceptance_criteria_strips_whitespace() -> None:
    body = "  - [ ]   AC-1: Some criterion  \n"
    result = _extract_acceptance_criteria(body)
    assert result == ["AC-1: Some criterion"]


# ---------- _pr_body ----------


def test_pr_body_includes_prd_path(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    ctx.prd.path = tmp_path / ".darkfactory" / "prds" / "PRD-001.md"
    ctx.prd.body = ""
    body = _pr_body(ctx)
    assert ".darkfactory/prds/PRD-001.md" in body


def test_pr_body_includes_ac_checklist(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    ctx.prd.body = "- [ ] AC-1: Do the thing\n- [ ] AC-2: Do more things\n"
    body = _pr_body(ctx)
    assert "- [ ] AC-1: Do the thing" in body
    assert "- [ ] AC-2: Do more things" in body
    assert "## Acceptance criteria" in body


def test_pr_body_no_ac_when_none(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    ctx.prd.body = "No criteria here."
    body = _pr_body(ctx)
    assert "## Acceptance criteria" not in body


def test_pr_body_includes_workflow_name(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    body = _pr_body(ctx)
    assert "test-workflow" in body


# ---------- dry-run path ----------


def test_dry_run_sets_pr_url(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    create_pr(ctx)
    assert ctx.pr_url == "https://example.test/dry-run/pr/0"


def test_dry_run_logs_command(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    create_pr(ctx)
    ctx.logger.info.assert_called()
    call_args = ctx.logger.info.call_args[0]
    assert "[dry-run]" in call_args[0]


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.operations.create_pr.gh_create_pr") as mock_create:
        create_pr(ctx)
    mock_create.assert_not_called()


# ---------- forbidden attribution ----------


def test_forbidden_attribution_in_title_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    ctx.prd.title = "Co-Authored-By: Claude Sonnet"
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        create_pr(ctx)


def test_forbidden_attribution_in_body_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    ctx.run_summary = "Generated with Claude Code"
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        create_pr(ctx)


# ---------- successful creation ----------


def test_successful_creation_calls_gh_pr_create(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch(
        "darkfactory.operations.create_pr.gh_create_pr",
        return_value=Ok("https://github.com/owner/repo/pull/42"),
    ) as mock_create:
        create_pr(ctx)

    mock_create.assert_called_once()
    args = mock_create.call_args
    assert args[0][0] == "main"  # base
    assert args[0][1] == "PRD-001: Test PR"  # title


def test_successful_creation_sets_pr_url(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch(
        "darkfactory.operations.create_pr.gh_create_pr",
        return_value=Ok("https://github.com/owner/repo/pull/42"),
    ):
        create_pr(ctx)

    assert ctx.pr_url == "https://github.com/owner/repo/pull/42"


def test_successful_creation_includes_title(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch(
        "darkfactory.operations.create_pr.gh_create_pr",
        return_value=Ok("https://github.com/owner/repo/pull/42"),
    ) as mock_create:
        create_pr(ctx)

    args = mock_create.call_args
    assert args[0][1] == "PRD-001: Test PR"
