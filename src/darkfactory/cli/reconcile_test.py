"""Tests for cli/reconcile.py — pure helper logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from darkfactory.cli.reconcile import (
    _build_reconcile_commit_msg,
    _extract_prd_id_from_path,
    _find_prd_file_for_branch,
)


# ---------- _extract_prd_id_from_path ----------


def test_extract_prd_id_simple() -> None:
    path = Path("PRD-224-some-title.md")
    assert _extract_prd_id_from_path(path) == "PRD-224"


def test_extract_prd_id_decimal() -> None:
    path = Path("PRD-224.7-reconcile-status.md")
    assert _extract_prd_id_from_path(path) == "PRD-224.7"


def test_extract_prd_id_no_match_returns_stem() -> None:
    path = Path("not-a-prd-file.md")
    assert _extract_prd_id_from_path(path) == "not-a-prd-file"


# ---------- _find_prd_file_for_branch ----------


def test_find_prd_file_for_branch_no_match_for_non_prd_branch(tmp_path: Path) -> None:
    result = _find_prd_file_for_branch("main", tmp_path)
    assert result is None


def test_find_prd_file_for_branch_no_match_when_file_absent(tmp_path: Path) -> None:
    result = _find_prd_file_for_branch("prd/PRD-999-some-feature", tmp_path)
    assert result is None


def test_find_prd_file_for_branch_returns_matching_file(tmp_path: Path) -> None:
    prd_file = tmp_path / "PRD-224.7-reconcile-status.md"
    prd_file.write_text("---\nstatus: review\n---\n")
    result = _find_prd_file_for_branch("prd/PRD-224.7-reconcile-status", tmp_path)
    assert result == prd_file


def test_find_prd_file_for_branch_returns_first_sorted(tmp_path: Path) -> None:
    a = tmp_path / "PRD-10-aaa.md"
    b = tmp_path / "PRD-10-bbb.md"
    a.write_text("---\nstatus: review\n---\n")
    b.write_text("---\nstatus: review\n---\n")
    result = _find_prd_file_for_branch("prd/PRD-10-aaa", tmp_path)
    assert result == a


# ---------- _build_reconcile_commit_msg ----------


def test_build_reconcile_commit_msg_single() -> None:
    prd_file = Path("PRD-224.7-reconcile-status.md")
    pr: dict[str, Any] = {"number": 42}
    candidates = [(prd_file, pr)]
    msg = _build_reconcile_commit_msg(candidates)
    assert "PRD-224.7" in msg
    assert "#42" in msg
    assert "[skip ci]" in msg


def test_build_reconcile_commit_msg_multiple() -> None:
    candidates = [
        (Path("PRD-1-foo.md"), {"number": 1}),
        (Path("PRD-2-bar.md"), {"number": 2}),
    ]
    msg = _build_reconcile_commit_msg(candidates)
    assert "reconcile 2 merged PRD statuses" in msg
    assert "[skip ci]" in msg
