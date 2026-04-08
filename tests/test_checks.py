"""Unit tests for darkfactory.checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from darkfactory.checks import Issue, validate_review_branches
from darkfactory.prd import load_all

from .conftest import write_prd


def _mock_git(present: set[str]) -> MagicMock:
    """Return a mock GitStateAdapter where only branches in ``present`` exist."""
    git = MagicMock()
    git.remote_branch_exists.side_effect = lambda branch: branch in present
    return git


# ---------- empty / no review PRDs ----------


def test_empty_prds_returns_no_issues(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "lone", status="ready")
    prds = load_all(tmp_prd_dir)
    git = _mock_git(set())
    assert validate_review_branches(prds, git) == []


def test_non_review_prds_ignored(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "alpha", status="ready")
    write_prd(tmp_prd_dir, "PRD-002", "beta", status="done")
    write_prd(tmp_prd_dir, "PRD-003", "gamma", status="blocked")
    prds = load_all(tmp_prd_dir)
    git = _mock_git(set())
    assert validate_review_branches(prds, git) == []


# ---------- review PRD, branch present ----------


def test_review_branch_present_returns_no_issues(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "my-feature", status="review")
    prds = load_all(tmp_prd_dir)
    git = _mock_git({"prd/PRD-001-my-feature"})
    assert validate_review_branches(prds, git) == []


# ---------- review PRD, branch gone ----------


def test_review_branch_gone_returns_one_issue(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "my-feature", status="review")
    prds = load_all(tmp_prd_dir)
    git = _mock_git(set())  # branch is absent
    issues = validate_review_branches(prds, git)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.prd_id == "PRD-001"
    assert issue.severity == "warning"
    assert "PRD-001" in issue.message
    assert "prd/PRD-001-my-feature" in issue.message


# ---------- multiple review PRDs, mixed ----------


def test_multiple_review_mixed_returns_correct_subset(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "alpha", status="review")
    write_prd(tmp_prd_dir, "PRD-002", "beta", status="review")
    write_prd(tmp_prd_dir, "PRD-003", "gamma", status="review")
    write_prd(tmp_prd_dir, "PRD-004", "delta", status="ready")
    prds = load_all(tmp_prd_dir)
    # Only PRD-002's branch is present; PRD-001 and PRD-003 are gone
    git = _mock_git({"prd/PRD-002-beta"})
    issues = validate_review_branches(prds, git)
    missing_ids = {i.prd_id for i in issues}
    assert missing_ids == {"PRD-001", "PRD-003"}
    assert all(i.severity == "warning" for i in issues)


# ---------- Issue dataclass ----------


def test_issue_fields() -> None:
    issue = Issue(prd_id="PRD-001", message="gone", severity="warning")
    assert issue.prd_id == "PRD-001"
    assert issue.message == "gone"
    assert issue.severity == "warning"
