"""Unit tests for cli/new.py — cmd_new, _slugify, _next_flat_prd_id."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from darkfactory.cli.new import _next_flat_prd_id, _slugify, cmd_new


# ---------- _slugify ----------


def test_slugify_basic() -> None:
    assert _slugify("Hello World") == "hello-world"


def test_slugify_special_chars_removed() -> None:
    assert _slugify("Add OAuth2.0 / Support!") == "add-oauth20-support"


def test_slugify_leading_trailing_whitespace() -> None:
    assert _slugify("  trim me  ") == "trim-me"


def test_slugify_multiple_spaces_become_single_dash() -> None:
    assert _slugify("a   b") == "a-b"


def test_slugify_empty_string_returns_untitled() -> None:
    assert _slugify("") == "untitled"


def test_slugify_only_special_chars_returns_untitled() -> None:
    assert _slugify("!!!") == "untitled"


# ---------- _next_flat_prd_id ----------


def test_next_flat_prd_id_empty_dict() -> None:
    assert _next_flat_prd_id({}) == "PRD-001"


def test_next_flat_prd_id_sequential() -> None:
    prds = {
        "PRD-001": MagicMock(),
        "PRD-002": MagicMock(),
        "PRD-003": MagicMock(),
    }
    assert _next_flat_prd_id(prds) == "PRD-004"


def test_next_flat_prd_id_with_gap() -> None:
    # Gaps don't matter — next is max + 1
    prds = {"PRD-001": MagicMock(), "PRD-005": MagicMock()}
    assert _next_flat_prd_id(prds) == "PRD-006"


def test_next_flat_prd_id_ignores_child_ids() -> None:
    # PRD-556.1 is a child id, not a flat id — should be ignored
    prds = {"PRD-001": MagicMock(), "PRD-556.1": MagicMock()}
    assert _next_flat_prd_id(prds) == "PRD-002"


def test_next_flat_prd_id_zero_pads_to_three_digits() -> None:
    prds = {f"PRD-{i:03d}": MagicMock() for i in range(1, 10)}
    assert _next_flat_prd_id(prds) == "PRD-010"


# ---------- cmd_new ----------


def _make_args(
    tmp_path: Path,
    title: str = "My New PRD",
    id: str | None = None,
    kind: str = "task",
    priority: str = "medium",
    effort: str = "m",
    capability: str = "moderate",
    open_: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        prd_dir=tmp_path / "prds",
        title=title,
        id=id,
        kind=kind,
        priority=priority,
        effort=effort,
        capability=capability,
        open=open_,
    )


def test_cmd_new_creates_file(tmp_path: Path) -> None:
    args = _make_args(tmp_path, title="My New PRD")
    result = cmd_new(args)
    assert result == 0
    prd_dir = tmp_path / "prds"
    files = list(prd_dir.glob("*.md"))
    assert len(files) == 1
    assert files[0].name.startswith("PRD-001-")


def test_cmd_new_file_contains_frontmatter(tmp_path: Path) -> None:
    args = _make_args(tmp_path, title="Test Title")
    cmd_new(args)
    prd_dir = tmp_path / "prds"
    content = next(prd_dir.glob("*.md")).read_text()
    assert "id: PRD-001" in content
    assert "title: Test Title" in content
    assert "status: draft" in content


def test_cmd_new_explicit_id(tmp_path: Path) -> None:
    args = _make_args(tmp_path, title="Explicit ID PRD", id="PRD-042")
    result = cmd_new(args)
    assert result == 0
    prd_dir = tmp_path / "prds"
    assert (prd_dir / "PRD-042-explicit-id-prd.md").exists()


def test_cmd_new_explicit_invalid_id_raises(tmp_path: Path) -> None:
    args = _make_args(tmp_path, title="Bad ID", id="NOT-VALID")
    with pytest.raises(SystemExit, match="invalid PRD id"):
        cmd_new(args)


def test_cmd_new_duplicate_id_raises(tmp_path: Path) -> None:
    args = _make_args(tmp_path, title="First PRD", id="PRD-010")
    cmd_new(args)
    args2 = _make_args(tmp_path, title="Second PRD", id="PRD-010")
    with pytest.raises(SystemExit, match="already exists"):
        cmd_new(args2)


def test_cmd_new_increments_id_sequentially(tmp_path: Path) -> None:
    cmd_new(_make_args(tmp_path, title="First"))
    cmd_new(_make_args(tmp_path, title="Second"))
    prd_dir = tmp_path / "prds"
    ids = sorted(f.name[:7] for f in prd_dir.glob("*.md"))
    assert ids == ["PRD-001", "PRD-002"]
