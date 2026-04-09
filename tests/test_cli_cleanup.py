"""Tests for `prd cleanup` subcommand and `prd status` hygiene line."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.checks import (
    StaleWorktree,
    find_stale_worktrees,
    is_safe_to_remove,
)
from darkfactory.cli import main

from .conftest import write_prd


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


def _make_worktree_dir(repo_root: Path, name: str) -> Path:
    """Create a fake worktree directory under .worktrees/."""
    wt = repo_root / ".worktrees" / name
    wt.mkdir(parents=True, exist_ok=True)
    return wt


# ---------- checks.find_stale_worktrees ----------


def test_find_stale_worktrees_no_dir(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # No .worktrees dir
    result = find_stale_worktrees(tmp_path)
    assert result == []


def test_find_stale_worktrees_returns_merged(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-001-some-feature")
    _make_worktree_dir(tmp_path, "PRD-002-another")

    fake_states = {
        "prd/PRD-001-some-feature": "MERGED",
        "prd/PRD-002-another": "OPEN",
    }

    with patch("darkfactory.checks._fetch_all_pr_states", return_value=fake_states):
        result = find_stale_worktrees(tmp_path)

    assert len(result) == 1
    assert result[0].prd_id == "PRD-001"
    assert result[0].branch == "prd/PRD-001-some-feature"
    assert result[0].pr_state == "MERGED"


def test_find_stale_worktrees_returns_closed(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-003-closed-one")

    fake_states = {"prd/PRD-003-closed-one": "CLOSED"}

    with patch("darkfactory.checks._fetch_all_pr_states", return_value=fake_states):
        result = find_stale_worktrees(tmp_path)

    assert len(result) == 1
    assert result[0].pr_state == "CLOSED"


def test_find_stale_worktrees_skips_open(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-005-open-one")

    fake_states = {"prd/PRD-005-open-one": "OPEN"}

    with patch("darkfactory.checks._fetch_all_pr_states", return_value=fake_states):
        result = find_stale_worktrees(tmp_path)

    assert result == []


# ---------- checks.is_safe_to_remove ----------


def _make_stale(
    tmp_path: Path,
    prd_id: str = "PRD-001",
    branch: str = "prd/PRD-001-slug",
    pr_state: str = "MERGED",
) -> StaleWorktree:
    wt_path = tmp_path / ".worktrees" / f"{prd_id}-slug"
    wt_path.mkdir(parents=True, exist_ok=True)
    return StaleWorktree(
        prd_id=prd_id,
        branch=branch,
        worktree_path=wt_path,
        pr_state=pr_state,
    )


def test_is_safe_open_pr_refuses(tmp_path: Path) -> None:
    wt = _make_stale(tmp_path, pr_state="OPEN")
    result = is_safe_to_remove(wt)
    assert not result.safe
    assert "open" in result.reason.lower()


def test_is_safe_unpushed_commits_refuses(tmp_path: Path) -> None:
    wt = _make_stale(tmp_path, pr_state="MERGED")
    with patch("darkfactory.checks._has_unpushed_commits", return_value=True):
        result = is_safe_to_remove(wt, force=False)
    assert not result.safe
    assert "unpushed" in result.reason.lower()


def test_is_safe_unpushed_with_force_allows(tmp_path: Path) -> None:
    wt = _make_stale(tmp_path, pr_state="MERGED")
    with patch("darkfactory.checks._has_unpushed_commits", return_value=True):
        result = is_safe_to_remove(wt, force=True)
    assert result.safe


def test_is_safe_merged_no_unpushed(tmp_path: Path) -> None:
    wt = _make_stale(tmp_path, pr_state="MERGED")
    with patch("darkfactory.checks._has_unpushed_commits", return_value=False):
        result = is_safe_to_remove(wt, force=False)
    assert result.safe


# ---------- cmd cleanup single ----------


def _setup_cleanup_env(tmp_path: Path) -> Path:
    """Set up a minimal repo with PRD dir and .git."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "my-feature", status="done")
    return prd_dir


def test_cleanup_single_merged_pr_removes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-001-my-feature")

    stale = StaleWorktree(
        prd_id="PRD-001",
        branch="prd/PRD-001-my-feature",
        worktree_path=tmp_path / ".worktrees" / "PRD-001-my-feature",
        pr_state="MERGED",
    )

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=stale),
        patch("darkfactory.checks._has_unpushed_commits", return_value=False),
        patch("darkfactory.cli._remove_worktree") as mock_remove,
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 0
    mock_remove.assert_called_once()
    out = capsys.readouterr().out
    assert "Removed" in out


def test_cleanup_single_open_pr_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-001-my-feature")

    stale = StaleWorktree(
        prd_id="PRD-001",
        branch="prd/PRD-001-my-feature",
        worktree_path=tmp_path / ".worktrees" / "PRD-001-my-feature",
        pr_state="OPEN",
    )

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=stale),
        patch("darkfactory.cli._remove_worktree") as mock_remove,
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 1
    mock_remove.assert_not_called()
    out = capsys.readouterr().out
    assert "Cannot remove" in out


def test_cleanup_single_unpushed_refuses_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-001-my-feature")

    stale = StaleWorktree(
        prd_id="PRD-001",
        branch="prd/PRD-001-my-feature",
        worktree_path=tmp_path / ".worktrees" / "PRD-001-my-feature",
        pr_state="MERGED",
    )

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=stale),
        patch("darkfactory.checks._has_unpushed_commits", return_value=True),
        patch("darkfactory.cli._remove_worktree") as mock_remove,
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 1
    mock_remove.assert_not_called()


def test_cleanup_single_unpushed_with_force_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)
    _make_worktree_dir(tmp_path, "PRD-001-my-feature")

    stale = StaleWorktree(
        prd_id="PRD-001",
        branch="prd/PRD-001-my-feature",
        worktree_path=tmp_path / ".worktrees" / "PRD-001-my-feature",
        pr_state="MERGED",
    )

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=stale),
        patch("darkfactory.checks._has_unpushed_commits", return_value=True),
        patch("darkfactory.cli._remove_worktree") as mock_remove,
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001", "--force"])

    assert rc == 0
    mock_remove.assert_called_once()


# ---------- cmd cleanup orphaned branch ----------


def test_cleanup_orphaned_branch_no_commits_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Force-removing an orphaned branch with 0 commits ahead succeeds."""
    prd_dir = _setup_cleanup_env(tmp_path)

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli._find_orphaned_branch",
            return_value="prd/PRD-001-my-feature",
        ),
        patch("darkfactory.cli._orphaned_branch_commit_count", return_value=0),
        patch("darkfactory.cli.subprocess"),
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001", "--force"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Removed orphaned branch" in out


def test_cleanup_orphaned_branch_with_commits_refuses_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Orphaned branch with commits ahead should refuse without --force."""
    prd_dir = _setup_cleanup_env(tmp_path)

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli._find_orphaned_branch",
            return_value="prd/PRD-001-my-feature",
        ),
        patch("darkfactory.cli._orphaned_branch_commit_count", return_value=3),
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "3 commit(s)" in out
    assert "--force" in out


def test_cleanup_orphaned_branch_with_commits_force_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Force-removing an orphaned branch with commits prints count."""
    prd_dir = _setup_cleanup_env(tmp_path)

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli._find_orphaned_branch",
            return_value="prd/PRD-001-my-feature",
        ),
        patch("darkfactory.cli._orphaned_branch_commit_count", return_value=5),
        patch("darkfactory.cli.subprocess"),
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001", "--force"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "5 commit(s) ahead of main" in out


def test_cleanup_no_worktree_no_branch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No worktree and no orphaned branch prints clear message."""
    prd_dir = _setup_cleanup_env(tmp_path)

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=None),
        patch("darkfactory.cli._find_orphaned_branch", return_value=None),
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "No worktree or orphaned branch found" in out


def test_cleanup_orphaned_branch_no_commits_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Orphaned branch with 0 commits ahead can be removed without --force."""
    prd_dir = _setup_cleanup_env(tmp_path)

    with (
        patch("darkfactory.cli._find_worktree_for_prd", return_value=None),
        patch(
            "darkfactory.cli._find_orphaned_branch",
            return_value="prd/PRD-001-my-feature",
        ),
        patch("darkfactory.cli._orphaned_branch_commit_count", return_value=0),
        patch("darkfactory.cli.subprocess"),
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "PRD-001"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Removed orphaned branch" in out


# ---------- cmd cleanup --merged ----------


def test_cleanup_merged_removes_only_merged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)

    stale_merged = StaleWorktree(
        prd_id="PRD-001",
        branch="prd/PRD-001-slug",
        worktree_path=tmp_path / ".worktrees" / "PRD-001-slug",
        pr_state="MERGED",
    )

    with (
        patch("darkfactory.cli.find_stale_worktrees", return_value=[stale_merged]),
        patch("darkfactory.checks._has_unpushed_commits", return_value=False),
        patch("darkfactory.cli._remove_worktree") as mock_remove,
    ):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "--merged"])

    assert rc == 0
    mock_remove.assert_called_once()


def test_cleanup_merged_no_stale_worktrees(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = _setup_cleanup_env(tmp_path)

    with patch("darkfactory.cli.find_stale_worktrees", return_value=[]):
        rc = main(["--prd-dir", str(prd_dir), "cleanup", "--merged"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "No stale" in out


# ---------- prd status hygiene line ----------


def test_status_shows_hygiene_line_when_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "feat", status="done")

    stale = [
        StaleWorktree(
            prd_id="PRD-001",
            branch="prd/PRD-001-feat",
            worktree_path=tmp_path / ".worktrees" / "PRD-001-feat",
            pr_state="MERGED",
        )
    ]

    with patch("darkfactory.cli.find_stale_worktrees", return_value=stale):
        rc = main(["--prd-dir", str(prd_dir), "status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "worktrees for merged PRDs" in out
    assert "prd cleanup --merged" in out


def test_status_hides_hygiene_line_when_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "feat", status="done")

    with patch("darkfactory.cli.find_stale_worktrees", return_value=[]):
        rc = main(["--prd-dir", str(prd_dir), "status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "worktrees for merged PRDs" not in out
