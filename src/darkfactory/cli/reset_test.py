"""Tests for cli.reset command."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from filelock import Timeout

from darkfactory.cli.reset import (
    _ArtifactSummary,
    _execute_reset,
    cmd_reset,
)
from darkfactory.model import load_one
from darkfactory.utils.git._types import Ok

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRD_FRONTMATTER = """\
---
id: PRD-99
title: Test PRD
kind: task
status: {status}
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts: []
workflow: task
assignee:
reviewers: []
target_version:
created: '2026-01-01'
updated: '2026-01-01'
tags: []
---

# Test PRD
"""


def _make_prd_file(data_dir: Path, status: str = "in-progress") -> Path:
    """Create a minimal PRD file and return its path."""
    prds_dir = data_dir / "prds"
    prds_dir.mkdir(parents=True, exist_ok=True)
    prd_file = prds_dir / "PRD-99-test-prd.md"
    prd_file.write_text(_PRD_FRONTMATTER.format(status=status), encoding="utf-8")
    return prd_file


def _make_args(
    data_dir: Path,
    prd_id: str = "PRD-99",
    execute: bool = False,
    yes: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=data_dir,
        prd_id=prd_id,
        execute=execute,
        yes=yes,
    )


# ---------------------------------------------------------------------------
# _ArtifactSummary
# ---------------------------------------------------------------------------


def test_artifact_summary_no_artifacts() -> None:
    s = _ArtifactSummary(prd_id="PRD-1", current_status="ready")
    assert not s.has_artifacts


def test_artifact_summary_with_worktree() -> None:
    s = _ArtifactSummary(
        prd_id="PRD-1",
        current_status="in-progress",
        worktree_path=Path("/tmp/wt"),
    )
    assert s.has_artifacts


def test_artifact_summary_with_open_prs() -> None:
    s = _ArtifactSummary(
        prd_id="PRD-1",
        current_status="ready",
        open_pr_numbers=[42],
    )
    assert s.has_artifacts


# ---------------------------------------------------------------------------
# cmd_reset — dry-run (AC-1)
# ---------------------------------------------------------------------------


def test_dry_run_prints_summary_no_mutations(tmp_path: Path) -> None:
    _make_prd_file(tmp_path, status="in-progress")
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch(
            "darkfactory.cli.reset._discover_artifacts",
            return_value=_ArtifactSummary(
                prd_id="PRD-99",
                current_status="in-progress",
                worktree_path=tmp_path / ".worktrees" / "PRD-99-test",
            ),
        ),
        patch("darkfactory.cli.reset._execute_reset") as mock_exec,
    ):
        result = cmd_reset(args)

    assert result == 0
    mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_reset — terminal status rejection (AC-11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["done", "cancelled", "superseded", "archived"])
def test_terminal_status_rejected(tmp_path: Path, status: str) -> None:
    _make_prd_file(tmp_path, status=status)
    args = _make_args(tmp_path)

    with patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path):
        result = cmd_reset(args)

    assert result == 1


# ---------------------------------------------------------------------------
# cmd_reset — unknown PRD
# ---------------------------------------------------------------------------


def test_unknown_prd_returns_1(tmp_path: Path) -> None:
    prds_dir = tmp_path / "prds"
    prds_dir.mkdir(parents=True)
    args = _make_args(tmp_path, prd_id="PRD-NONEXISTENT")

    with patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path):
        result = cmd_reset(args)

    assert result == 1


# ---------------------------------------------------------------------------
# cmd_reset — nothing to reset (AC-3)
# ---------------------------------------------------------------------------


def test_nothing_to_reset_exits_cleanly(tmp_path: Path) -> None:
    _make_prd_file(tmp_path, status="ready")
    args = _make_args(tmp_path, execute=True, yes=True)

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch(
            "darkfactory.cli.reset._discover_artifacts",
            return_value=_ArtifactSummary(
                prd_id="PRD-99",
                current_status="ready",
            ),
        ),
    ):
        result = cmd_reset(args)

    assert result == 0


# ---------------------------------------------------------------------------
# cmd_reset — execute mode with confirmation (AC-2)
# ---------------------------------------------------------------------------


def test_execute_with_yes_skips_prompt(tmp_path: Path) -> None:
    """AC-4: --execute --yes skips confirmation."""
    _make_prd_file(tmp_path, status="in-progress")
    args = _make_args(tmp_path, execute=True, yes=True)

    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
        local_branches=["prd/PRD-99-test-prd"],
    )

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.reset._discover_artifacts", return_value=summary),
        patch("darkfactory.cli.reset.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.cli.reset._execute_reset",
            return_value=(["deleted local branch"], []),
        ),
        patch("darkfactory.cli.reset.EventWriter") as mock_writer_cls,
        patch("builtins.input") as mock_input,
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        result = cmd_reset(args)

    assert result == 0
    mock_input.assert_not_called()


def test_execute_aborts_on_no_confirm(tmp_path: Path) -> None:
    _make_prd_file(tmp_path, status="in-progress")
    args = _make_args(tmp_path, execute=True, yes=False)

    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
        local_branches=["prd/PRD-99-test-prd"],
    )

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.reset._discover_artifacts", return_value=summary),
        patch("darkfactory.cli.reset.FileLock") as mock_lock_cls,
        patch("builtins.input", return_value="n"),
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock

        result = cmd_reset(args)

    assert result == 1


# ---------------------------------------------------------------------------
# cmd_reset — lock held (AC-12)
# ---------------------------------------------------------------------------


def test_lock_held_aborts(tmp_path: Path) -> None:
    _make_prd_file(tmp_path, status="in-progress")
    args = _make_args(tmp_path, execute=True, yes=True)

    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
        local_branches=["prd/PRD-99-test-prd"],
    )

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.reset._discover_artifacts", return_value=summary),
        patch("darkfactory.cli.reset.FileLock") as mock_lock_cls,
    ):
        mock_lock = MagicMock()
        mock_lock.acquire.side_effect = Timeout(
            str(tmp_path / ".worktrees" / "PRD-99.lock")
        )
        mock_lock_cls.return_value = mock_lock

        result = cmd_reset(args)

    assert result == 1


# ---------------------------------------------------------------------------
# _execute_reset — partial artifacts (AC-5)
# ---------------------------------------------------------------------------


def test_execute_reset_partial_artifacts(tmp_path: Path) -> None:
    """AC-5: Only present artifacts are cleaned, missing ones skipped."""
    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
        # No worktree, no PRs, just a local branch and rework guard
        local_branches=["prd/PRD-99-test-prd"],
        has_rework_guard=True,
    )

    with (
        patch("subprocess.run"),
        patch("darkfactory.cli.reset.git_run") as mock_git_run,
        patch("darkfactory.cli.reset.ReworkGuard") as mock_guard_cls,
        patch("darkfactory.cli.reset.load_one") as mock_load,
        patch("darkfactory.cli.reset.set_status"),
    ):
        mock_git_run.return_value = Ok(None)
        mock_guard = MagicMock()
        mock_guard_cls.return_value = mock_guard
        mock_prd = MagicMock()
        mock_load.return_value = mock_prd

        cleaned, skipped = _execute_reset(summary, tmp_path, tmp_path)

    assert any("local branch" in c for c in cleaned)
    assert any("rework guard" in c for c in cleaned)
    assert any("status" in c for c in cleaned)
    mock_guard.reset.assert_called_once_with("PRD-99")


# ---------------------------------------------------------------------------
# _execute_reset — event emission (AC-10)
# ---------------------------------------------------------------------------


def test_event_emitted_on_execute(tmp_path: Path) -> None:
    """AC-10: A cli/prd_reset event is emitted on execute."""
    _make_prd_file(tmp_path, status="in-progress")
    args = _make_args(tmp_path, execute=True, yes=True)

    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
        has_rework_guard=True,
    )

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.reset._discover_artifacts", return_value=summary),
        patch("darkfactory.cli.reset.FileLock") as mock_lock_cls,
        patch(
            "darkfactory.cli.reset._execute_reset",
            return_value=(["cleared rework guard"], []),
        ),
        patch("darkfactory.cli.reset.EventWriter") as mock_writer_cls,
    ):
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        result = cmd_reset(args)

    assert result == 0
    mock_writer.emit.assert_called_once_with(
        "cli",
        "prd_reset",
        cleaned=["cleared rework guard"],
        skipped=[],
    )
    mock_writer.close.assert_called_once()


# ---------------------------------------------------------------------------
# _execute_reset — PR closing (AC-6)
# ---------------------------------------------------------------------------


def test_execute_reset_closes_prs(tmp_path: Path) -> None:
    """AC-6: All open PRs are closed with attribution comment."""
    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="ready",
        open_pr_numbers=[10, 20],
    )

    with (
        patch("subprocess.run") as mock_subprocess,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)

        cleaned, skipped = _execute_reset(summary, tmp_path, tmp_path)

    # Both PRs should be in cleaned
    assert any("#10" in c for c in cleaned)
    assert any("#20" in c for c in cleaned)
    # Filter to gh pr close calls only (git commands also go through subprocess now)
    gh_calls = [c for c in mock_subprocess.call_args_list if c[0][0][0] == "gh"]
    assert len(gh_calls) == 2
    # Verify comment content
    first_call = gh_calls[0]
    cmd_list = first_call[0][0]
    assert "close" in cmd_list
    assert "--comment" in cmd_list
    comment_idx = cmd_list.index("--comment")
    assert "prd reset" in cmd_list[comment_idx + 1]


# ---------------------------------------------------------------------------
# _execute_reset — workflow preserved (AC-7)
# ---------------------------------------------------------------------------


def test_workflow_preserved_after_reset(tmp_path: Path) -> None:
    """AC-7: workflow field in frontmatter is preserved after reset."""
    _make_prd_file(tmp_path, status="in-progress")
    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="in-progress",
    )

    cleaned, skipped = _execute_reset(summary, tmp_path, tmp_path)

    prd = load_one(tmp_path, "PRD-99")
    assert prd.workflow == "task"
    assert prd.status == "ready"


# ---------------------------------------------------------------------------
# _execute_reset — updated timestamp (AC-9)
# ---------------------------------------------------------------------------


def test_updated_timestamp_set(tmp_path: Path) -> None:
    """AC-9: reset stamps the updated field to today's date."""
    _make_prd_file(tmp_path, status="review")
    summary = _ArtifactSummary(
        prd_id="PRD-99",
        current_status="review",
    )

    cleaned, skipped = _execute_reset(summary, tmp_path, tmp_path)

    prd = load_one(tmp_path, "PRD-99")
    from datetime import date

    assert prd.updated == date.today().isoformat()
    assert any("status" in c for c in cleaned)


# ---------------------------------------------------------------------------
# cmd_reset — draft/ready warning
# ---------------------------------------------------------------------------


def test_draft_status_warns_but_probes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_prd_file(tmp_path, status="draft")
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.reset._find_repo_root", return_value=tmp_path),
        patch(
            "darkfactory.cli.reset._discover_artifacts",
            return_value=_ArtifactSummary(prd_id="PRD-99", current_status="draft"),
        ),
    ):
        result = cmd_reset(args)

    assert result == 0
    captured = capsys.readouterr()
    assert "no workflow has run" in captured.out
