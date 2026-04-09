"""Tests for ``prd reconcile`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from darkfactory.cli import main

from .conftest import write_prd


def _init_git_repo(path: Path) -> None:
    """Create a bare .git dir so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


def _fake_pr(head_ref: str, number: int) -> dict[str, Any]:
    return {
        "headRefName": head_ref,
        "mergedAt": "2026-04-08T00:00:00Z",
        "number": number,
    }


# ---------------------------------------------------------------------------
# Dry-run (no --execute)
# ---------------------------------------------------------------------------


def test_reconcile_dryrun_lists_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dry-run with one candidate prints the change but makes no modifications."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    prd_file = write_prd(prd_dir, "PRD-224", "reconcile-test", status="review")
    original_text = prd_file.read_text()

    prs = [_fake_pr("prd/PRD-224-reconcile-test", 42)]

    with patch("darkfactory.cli._get_merged_prd_prs", return_value=prs):
        rc = main(["--prd-dir", str(prd_dir), "reconcile"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-224" in out
    assert "review -> done" in out
    assert "#42" in out
    assert "Dry run" in out
    # File must not be modified.
    assert prd_file.read_text() == original_text


def test_reconcile_dryrun_no_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When no PRDs need reconciling, the command prints 'up to date'."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    # PRD is already 'done', not 'review'.
    write_prd(prd_dir, "PRD-001", "done-already", status="done")

    prs = [_fake_pr("prd/PRD-001-done-already", 10)]

    with patch("darkfactory.cli._get_merged_prd_prs", return_value=prs):
        rc = main(["--prd-dir", str(prd_dir), "reconcile"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "up to date" in out


def test_reconcile_dryrun_no_matching_prs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When merged PRs have no matching PRD file, prints 'up to date'."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()

    prs = [_fake_pr("prd/PRD-999-nonexistent", 99)]

    with patch("darkfactory.cli._get_merged_prd_prs", return_value=prs):
        rc = main(["--prd-dir", str(prd_dir), "reconcile"])

    assert rc == 0
    assert "up to date" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --execute path
# ---------------------------------------------------------------------------


def test_reconcile_execute_flips_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--execute flips status from 'review' to 'done' and updates the updated field."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    prd_file = write_prd(prd_dir, "PRD-010", "my-feature", status="review")

    prs = [_fake_pr("prd/PRD-010-my-feature", 7)]

    with (
        patch("darkfactory.cli._get_merged_prd_prs", return_value=prs),
        patch("darkfactory.cli._create_reconcile_pr"),
    ):
        rc = main(["--prd-dir", str(prd_dir), "reconcile", "--execute"])

    assert rc == 0
    text = prd_file.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["status"] == "done"
    # updated field should be today's date string
    from datetime import date

    assert str(fm["updated"]) == date.today().isoformat()


def test_reconcile_execute_creates_pr(
    tmp_path: Path,
) -> None:
    """--execute without --commit-to-main calls _create_reconcile_pr."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-020", "pr-test", status="review")

    prs = [_fake_pr("prd/PRD-020-pr-test", 20)]

    mock_create_pr = MagicMock()

    with (
        patch("darkfactory.cli._get_merged_prd_prs", return_value=prs),
        patch("darkfactory.cli._create_reconcile_pr", mock_create_pr),
    ):
        rc = main(["--prd-dir", str(prd_dir), "reconcile", "--execute"])

    assert rc == 0
    assert mock_create_pr.called


# ---------------------------------------------------------------------------
# --execute --commit-to-main
# ---------------------------------------------------------------------------


def test_reconcile_execute_commit_to_main(
    tmp_path: Path,
) -> None:
    """--execute --commit-to-main calls _commit_to_main instead of _create_reconcile_pr."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-030", "direct-commit", status="review")

    prs = [_fake_pr("prd/PRD-030-direct-commit", 30)]

    mock_commit = MagicMock()
    mock_create_pr = MagicMock()

    with (
        patch("darkfactory.cli._get_merged_prd_prs", return_value=prs),
        patch("darkfactory.cli._commit_to_main", mock_commit),
        patch("darkfactory.cli._create_reconcile_pr", mock_create_pr),
    ):
        rc = main(
            ["--prd-dir", str(prd_dir), "reconcile", "--execute", "--commit-to-main"]
        )

    assert rc == 0
    assert mock_commit.called
    assert not mock_create_pr.called


# ---------------------------------------------------------------------------
# Multiple candidates — batched commit
# ---------------------------------------------------------------------------


def test_reconcile_multiple_candidates_batched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Multiple PRDs are reported in a single dry-run list."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-100", "alpha", status="review")
    write_prd(prd_dir, "PRD-101", "beta", status="review")

    prs = [
        _fake_pr("prd/PRD-100-alpha", 100),
        _fake_pr("prd/PRD-101-beta", 101),
    ]

    with patch("darkfactory.cli._get_merged_prd_prs", return_value=prs):
        rc = main(["--prd-dir", str(prd_dir), "reconcile"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-100" in out
    assert "PRD-101" in out


def test_reconcile_multiple_execute_batched_commit_msg(
    tmp_path: Path,
) -> None:
    """Multiple candidates produce a batched commit message."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-200", "first", status="review")
    write_prd(prd_dir, "PRD-201", "second", status="review")

    prs = [
        _fake_pr("prd/PRD-200-first", 200),
        _fake_pr("prd/PRD-201-second", 201),
    ]

    captured_msg: list[str] = []

    def fake_commit(
        candidates: list[tuple[Path, dict[str, Any]]], repo_root: Path
    ) -> None:
        from darkfactory.cli import _build_reconcile_commit_msg

        captured_msg.append(_build_reconcile_commit_msg(candidates))

    with (
        patch("darkfactory.cli._get_merged_prd_prs", return_value=prs),
        patch("darkfactory.cli._create_reconcile_pr", fake_commit),
    ):
        rc = main(["--prd-dir", str(prd_dir), "reconcile", "--execute"])

    assert rc == 0
    assert len(captured_msg) == 1
    assert "reconcile 2 merged PRD statuses" in captured_msg[0]
    assert "[skip ci]" in captured_msg[0]


def test_reconcile_single_commit_msg_format(
    tmp_path: Path,
) -> None:
    """Single candidate produces per-PRD commit message with PR number."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-300", "single", status="review")

    prs = [_fake_pr("prd/PRD-300-single", 55)]

    captured_msg: list[str] = []

    def fake_commit(
        candidates: list[tuple[Path, dict[str, Any]]], repo_root: Path
    ) -> None:
        from darkfactory.cli import _build_reconcile_commit_msg

        captured_msg.append(_build_reconcile_commit_msg(candidates))

    with (
        patch("darkfactory.cli._get_merged_prd_prs", return_value=prs),
        patch("darkfactory.cli._create_reconcile_pr", fake_commit),
    ):
        rc = main(["--prd-dir", str(prd_dir), "reconcile", "--execute"])

    assert rc == 0
    assert len(captured_msg) == 1
    msg = captured_msg[0]
    assert "PRD-300" in msg
    assert "#55" in msg
    assert "auto-reconciled" in msg
    assert "[skip ci]" in msg
