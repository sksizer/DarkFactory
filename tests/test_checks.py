"""Unit tests for darkfactory.checks."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.checks import (
    Issue,
    ResumeStatus,
    is_resume_safe,
    validate_review_branches,
)
from darkfactory.model import load_all
from darkfactory.utils._result import Ok as _Ok
from darkfactory.utils.git import GitErr as _GitErr
from darkfactory.utils.github import GhErr as _GhErr

from .conftest import write_prd


def _mock_git(present: set[str]) -> MagicMock:
    """Return a mock GitStateAdapter where only branches in ``present`` exist."""
    git = MagicMock()
    git.remote_branch_exists.side_effect = lambda branch: branch in present
    return git


# ---------- empty / no review PRDs ----------


def test_empty_prds_returns_no_issues(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "lone", status="ready")
    prds = load_all(tmp_data_dir)
    git = _mock_git(set())
    assert validate_review_branches(prds, git) == []


def test_non_review_prds_ignored(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "alpha", status="ready")
    write_prd(tmp_data_dir / "prds", "PRD-002", "beta", status="done")
    write_prd(tmp_data_dir / "prds", "PRD-003", "gamma", status="blocked")
    prds = load_all(tmp_data_dir)
    git = _mock_git(set())
    assert validate_review_branches(prds, git) == []


# ---------- review PRD, branch present ----------


def test_review_branch_present_returns_no_issues(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "my-feature", status="review")
    prds = load_all(tmp_data_dir)
    git = _mock_git({"prd/PRD-001-my-feature"})
    assert validate_review_branches(prds, git) == []


# ---------- review PRD, branch gone ----------


def test_review_branch_gone_returns_one_issue(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "my-feature", status="review")
    prds = load_all(tmp_data_dir)
    git = _mock_git(set())  # branch is absent
    issues = validate_review_branches(prds, git)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.prd_id == "PRD-001"
    assert issue.severity == "warning"
    assert "PRD-001" in issue.message
    assert "prd/PRD-001-my-feature" in issue.message


# ---------- multiple review PRDs, mixed ----------


def test_multiple_review_mixed_returns_correct_subset(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "alpha", status="review")
    write_prd(tmp_data_dir / "prds", "PRD-002", "beta", status="review")
    write_prd(tmp_data_dir / "prds", "PRD-003", "gamma", status="review")
    write_prd(tmp_data_dir / "prds", "PRD-004", "delta", status="ready")
    prds = load_all(tmp_data_dir)
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


# ---------- is_resume_safe ----------


_GIT_REF_NOT_FOUND = _GitErr(128, "", "", ["git"])


def test_is_resume_safe_open_pr_returns_safe(tmp_path: Path) -> None:
    """An open PR should not block resuming."""
    with (
        patch(
            "darkfactory.checks.get_resume_pr_state",
            return_value=_Ok([{"state": "OPEN", "mergedAt": None}]),
        ),
        patch("darkfactory.checks.git_run", return_value=_GIT_REF_NOT_FOUND),
    ):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert status.kind == "safe"


def test_is_resume_safe_merged_pr_returns_not_safe(tmp_path: Path) -> None:
    """A merged PR must block resuming."""
    with (
        patch(
            "darkfactory.checks.get_resume_pr_state",
            return_value=_Ok(
                [{"state": "MERGED", "mergedAt": "2026-01-01T00:00:00Z"}]
            ),
        ),
        patch("darkfactory.checks.git_run", return_value=_GIT_REF_NOT_FOUND),
    ):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is False
    assert status.kind == "pr_merged"
    assert "prd cleanup" in status.reason


def test_is_resume_safe_closed_pr_returns_not_safe(tmp_path: Path) -> None:
    """A closed (not merged) PR must block resuming."""
    with (
        patch(
            "darkfactory.checks.get_resume_pr_state",
            return_value=_Ok([{"state": "CLOSED", "mergedAt": None}]),
        ),
        patch("darkfactory.checks.git_run", return_value=_GIT_REF_NOT_FOUND),
    ):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is False
    assert status.kind == "pr_closed"
    assert "prd cleanup" in status.reason


def test_is_resume_safe_no_prs_returns_safe(tmp_path: Path) -> None:
    """No PRs at all means we can safely resume."""
    with (
        patch("darkfactory.checks.get_resume_pr_state", return_value=_Ok([])),
        patch("darkfactory.checks.git_run", return_value=_GIT_REF_NOT_FOUND),
    ):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True


def test_is_resume_safe_no_gh_degrades_gracefully(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing gh binary should warn and proceed with local-only checks."""
    with caplog.at_level(logging.WARNING, logger="darkfactory.checks"):
        with (
            patch(
                "darkfactory.checks.get_resume_pr_state",
                return_value=_GhErr(-1, "", "gh not found", ["gh"]),
            ),
            patch(
                "darkfactory.checks.git_run", return_value=_GIT_REF_NOT_FOUND
            ),
        ):
            status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert any("gh not found" in rec.message for rec in caplog.records)


def test_is_resume_safe_diverged_warns_but_allows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Branch behind origin should warn but not block resume."""
    git_responses = [
        _Ok(None, stdout="aaaa1111\n"),  # rev-parse refs/heads/...
        _Ok(None, stdout="bbbb2222\n"),  # rev-parse refs/remotes/origin/...
        _Ok(None, stdout="3\n"),  # rev-list --count
    ]

    with caplog.at_level(logging.WARNING, logger="darkfactory.checks"):
        with (
            patch(
                "darkfactory.checks.get_resume_pr_state",
                return_value=_Ok([]),
            ),
            patch(
                "darkfactory.checks.git_run", side_effect=git_responses
            ),
        ):
            status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert status.kind == "diverged"
    assert any("behind" in rec.message for rec in caplog.records)


def test_resume_status_dataclass() -> None:
    s = ResumeStatus(safe=True, reason="", kind="safe")
    assert s.safe is True
    assert s.reason == ""
    assert s.kind == "safe"
