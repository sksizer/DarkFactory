"""Unit tests for create_pr builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.engine import PrResult, PrdWorkflowRun
from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.create_pr import (
    _extract_acceptance_criteria,
    _pr_body_from_prd,
    create_pr,
)
from darkfactory.utils import Ok
from darkfactory.workflow import RunContext


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> RunContext:
    """Build a RunContext for create_pr tests."""
    ctx = make_builtin_ctx(tmp_path, dry_run=dry_run)
    # Override PRD body/title/path for create_pr-specific needs.
    ctx.state.get(PrdWorkflowRun)
    from darkfactory.operations._test_helpers import _make_test_prd

    prd = _make_test_prd(prd_id="PRD-001", title="Test PR", repo_root=tmp_path)
    # Create a prd path file so relative_to works
    prd_path = tmp_path / ".darkfactory" / "prds" / "PRD-001-test.md"
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    prd_path.touch()
    from darkfactory.model import PRD

    prd = PRD(
        id="PRD-001",
        path=prd_path,
        slug="test",
        title="Test PR",
        kind="task",
        status="ready",
        priority="medium",
        effort="s",
        capability="simple",
        parent=None,
        depends_on=[],
        blocks=[],
        impacts=[],
        workflow=None,
        assignee=None,
        reviewers=[],
        target_version=None,
        created="2026-04-06",
        updated="2026-04-06",
        tags=[],
        raw_frontmatter={},
        body="",
    )
    from darkfactory.workflow import Workflow

    ctx.state.put(
        PrdWorkflowRun(prd=prd, workflow=Workflow(name="test-workflow", tasks=[]))
    )
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


# ---------- _pr_body_from_prd ----------


def test_pr_body_includes_prd_path(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    prd_run = ctx.state.get(PrdWorkflowRun)
    body = _pr_body_from_prd(ctx, prd_run)
    assert ".darkfactory/prds/PRD-001-test.md" in body


def test_pr_body_includes_ac_checklist(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    prd_run = ctx.state.get(PrdWorkflowRun)
    from darkfactory.model import PRD
    from darkfactory.workflow import Workflow

    prd = PRD(
        id="PRD-001",
        path=prd_run.prd.path,
        slug="test",
        title="Test PR",
        kind="task",
        status="ready",
        priority="medium",
        effort="s",
        capability="simple",
        parent=None,
        depends_on=[],
        blocks=[],
        impacts=[],
        workflow=None,
        assignee=None,
        reviewers=[],
        target_version=None,
        created="2026-04-06",
        updated="2026-04-06",
        tags=[],
        raw_frontmatter={},
        body="- [ ] AC-1: Do the thing\n- [ ] AC-2: Do more things\n",
    )
    ctx.state.put(
        PrdWorkflowRun(prd=prd, workflow=Workflow(name="test-workflow", tasks=[]))
    )
    prd_run = ctx.state.get(PrdWorkflowRun)
    body = _pr_body_from_prd(ctx, prd_run)
    assert "- [ ] AC-1: Do the thing" in body
    assert "- [ ] AC-2: Do more things" in body
    assert "## Acceptance criteria" in body


def test_pr_body_no_ac_when_none(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    prd_run = ctx.state.get(PrdWorkflowRun)
    body = _pr_body_from_prd(ctx, prd_run)
    assert "## Acceptance criteria" not in body


def test_pr_body_includes_workflow_name(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    prd_run = ctx.state.get(PrdWorkflowRun)
    body = _pr_body_from_prd(ctx, prd_run)
    assert "test-workflow" in body


# ---------- dry-run path ----------


def test_dry_run_sets_pr_url(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    create_pr(ctx)
    assert ctx.state.get(PrResult).url == "https://example.test/dry-run/pr/0"


def test_dry_run_no_subprocess_calls(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.operations.create_pr.gh_create_pr") as mock_create:
        create_pr(ctx)
    mock_create.assert_not_called()


# ---------- forbidden attribution ----------


def test_forbidden_attribution_in_title_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    prd_run = ctx.state.get(PrdWorkflowRun)
    from darkfactory.model import PRD
    from darkfactory.workflow import Workflow

    bad_prd = PRD(
        id="PRD-001",
        path=prd_run.prd.path,
        slug="test",
        title="Co-Authored-By: Claude Sonnet",
        kind="task",
        status="ready",
        priority="medium",
        effort="s",
        capability="simple",
        parent=None,
        depends_on=[],
        blocks=[],
        impacts=[],
        workflow=None,
        assignee=None,
        reviewers=[],
        target_version=None,
        created="2026-04-06",
        updated="2026-04-06",
        tags=[],
        raw_frontmatter={},
        body="",
    )
    ctx.state.put(
        PrdWorkflowRun(prd=bad_prd, workflow=Workflow(name="test-workflow", tasks=[]))
    )
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        create_pr(ctx)


def test_forbidden_attribution_in_body_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    prd_run = ctx.state.get(PrdWorkflowRun)
    ctx.state.put(
        PrdWorkflowRun(
            prd=prd_run.prd,
            workflow=prd_run.workflow,
            run_summary="Generated with Claude Code",
        )
    )
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

    assert ctx.state.get(PrResult).url == "https://github.com/owner/repo/pull/42"


def test_successful_creation_includes_title(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    with patch(
        "darkfactory.operations.create_pr.gh_create_pr",
        return_value=Ok("https://github.com/owner/repo/pull/42"),
    ) as mock_create:
        create_pr(ctx)

    args = mock_create.call_args
    assert args[0][1] == "PRD-001: Test PR"
