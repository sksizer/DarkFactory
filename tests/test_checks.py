"""Unit tests for darkfactory.checks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.checks import (
    Issue,
    ResumeStatus,
    is_resume_safe,
    validate_review_branches,
)
from darkfactory.model import load_all

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


# ---------- is_resume_safe ----------


def _make_gh_run(prs: list[dict[str, Any]]) -> MagicMock:
    """Return a mock for subprocess.run that yields a gh response with ``prs``."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(prs)
    return mock


def _make_git_rev_parse_not_found() -> MagicMock:
    """Return a mock for subprocess.run that simulates refs not found."""
    mock = MagicMock()
    mock.returncode = 128
    mock.stdout = ""
    return mock


def test_is_resume_safe_open_pr_returns_safe(tmp_path: Path) -> None:
    """An open PR should not block resuming."""
    open_pr = [{"state": "OPEN", "mergedAt": None}]

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gh":
            return _make_gh_run(open_pr)
        # git rev-parse for divergence check: no remote ref
        return _make_git_rev_parse_not_found()

    with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert status.kind == "safe"


def test_is_resume_safe_merged_pr_returns_not_safe(tmp_path: Path) -> None:
    """A merged PR must block resuming."""
    merged_pr = [{"state": "MERGED", "mergedAt": "2026-01-01T00:00:00Z"}]

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gh":
            return _make_gh_run(merged_pr)
        return _make_git_rev_parse_not_found()

    with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is False
    assert status.kind == "pr_merged"
    assert "prd cleanup" in status.reason


def test_is_resume_safe_closed_pr_returns_not_safe(tmp_path: Path) -> None:
    """A closed (not merged) PR must block resuming."""
    closed_pr = [{"state": "CLOSED", "mergedAt": None}]

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gh":
            return _make_gh_run(closed_pr)
        return _make_git_rev_parse_not_found()

    with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is False
    assert status.kind == "pr_closed"
    assert "prd cleanup" in status.reason


def test_is_resume_safe_no_prs_returns_safe(tmp_path: Path) -> None:
    """No PRs at all means we can safely resume."""

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gh":
            return _make_gh_run([])
        return _make_git_rev_parse_not_found()

    with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
        status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True


def test_is_resume_safe_no_gh_degrades_gracefully(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing gh binary should warn and proceed with local-only checks."""

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "gh":
            raise FileNotFoundError("gh not found")
        return _make_git_rev_parse_not_found()

    with caplog.at_level(logging.WARNING, logger="darkfactory.checks"):
        with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
            status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert any("gh not found" in rec.message for rec in caplog.records)


def test_is_resume_safe_diverged_warns_but_allows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Branch behind origin should warn but not block resume."""
    call_count = 0

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if cmd[0] == "gh":
            return _make_gh_run([])  # no PRs
        # git rev-parse for local ref
        if "refs/heads/" in " ".join(cmd):
            m = MagicMock()
            m.returncode = 0
            m.stdout = "aaaa1111\n"
            return m
        # git rev-parse for remote ref
        if "refs/remotes/" in " ".join(cmd):
            m = MagicMock()
            m.returncode = 0
            m.stdout = "bbbb2222\n"
            return m
        # git rev-list --count for behind count
        if "rev-list" in cmd:
            m = MagicMock()
            m.returncode = 0
            m.stdout = "3\n"
            return m
        return _make_git_rev_parse_not_found()

    with caplog.at_level(logging.WARNING, logger="darkfactory.checks"):
        with patch("darkfactory.checks.subprocess.run", side_effect=fake_run):
            status = is_resume_safe("prd/PRD-001-my-feat", tmp_path)

    assert status.safe is True
    assert status.kind == "diverged"
    assert any("behind" in rec.message for rec in caplog.records)


def test_resume_status_dataclass() -> None:
    s = ResumeStatus(safe=True, reason="", kind="safe")
    assert s.safe is True
    assert s.reason == ""
    assert s.kind == "safe"
