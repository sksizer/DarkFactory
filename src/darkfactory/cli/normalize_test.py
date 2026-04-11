"""Tests for cli.normalize helpers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.normalize import (
    _NORMALIZABLE_FIELDS,
    _normalize_prd,
    cmd_normalize,
)


# ---------- _normalize_prd ----------


def _make_prd(
    prd_id: str = "PRD-001",
    path: Path | None = None,
    raw_frontmatter: dict[str, Any] | None = None,
) -> MagicMock:
    prd = MagicMock()
    prd.id = prd_id
    prd.path = path or Path(f"/fake/{prd_id}.md")
    prd.raw_frontmatter = raw_frontmatter or {}
    return prd


def test_normalize_prd_returns_false_when_no_list_fields() -> None:
    prd = _make_prd(raw_frontmatter={"title": "My PRD", "status": "ready"})
    result = _normalize_prd(prd, check_only=False)
    assert result is False


def test_normalize_prd_skips_non_list_field() -> None:
    prd = _make_prd(raw_frontmatter={"tags": "not-a-list"})
    with patch("darkfactory.cli.normalize.normalize_list_field_at") as mock_norm:
        result = _normalize_prd(prd, check_only=False)
    mock_norm.assert_not_called()
    assert result is False


def test_normalize_prd_calls_normalize_for_list_fields() -> None:
    prd = _make_prd(raw_frontmatter={"tags": ["z-tag", "a-tag"]})
    with patch(
        "darkfactory.cli.normalize.normalize_list_field_at", return_value=True
    ) as mock_norm:
        result = _normalize_prd(prd, check_only=False)
    mock_norm.assert_called_once_with(prd.path, "tags", ["z-tag", "a-tag"], write=True)
    assert result is True


def test_normalize_prd_check_only_passes_write_false() -> None:
    prd = _make_prd(raw_frontmatter={"impacts": ["b", "a"]})
    with patch(
        "darkfactory.cli.normalize.normalize_list_field_at", return_value=True
    ) as mock_norm:
        _normalize_prd(prd, check_only=True)
    mock_norm.assert_called_once_with(prd.path, "impacts", ["b", "a"], write=False)


def test_normalize_prd_handles_value_error(capsys: pytest.CaptureFixture[str]) -> None:
    prd = _make_prd(raw_frontmatter={"tags": ["x"]})
    with patch(
        "darkfactory.cli.normalize.normalize_list_field_at",
        side_effect=ValueError("bad field"),
    ):
        result = _normalize_prd(prd, check_only=False)
    assert result is False
    captured = capsys.readouterr()
    assert "WARNING: bad field" in captured.err


def test_normalize_prd_processes_all_normalizable_fields() -> None:
    raw = {field: ["b", "a"] for field in _NORMALIZABLE_FIELDS}
    prd = _make_prd(raw_frontmatter=raw)
    with patch(
        "darkfactory.cli.normalize.normalize_list_field_at", return_value=False
    ) as mock_norm:
        _normalize_prd(prd, check_only=False)
    assert mock_norm.call_count == len(_NORMALIZABLE_FIELDS)


# ---------- cmd_normalize ----------


def test_cmd_normalize_unknown_prd_id_raises(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id="PRD-999", all=False, check=False
    )
    with patch("darkfactory.cli.normalize._load", return_value={}):
        with pytest.raises(SystemExit, match="unknown PRD id"):
            cmd_normalize(args)


def test_cmd_normalize_no_target_raises(tmp_path: Path) -> None:
    args = argparse.Namespace(data_dir=tmp_path, prd_id=None, all=False, check=False)
    with patch("darkfactory.cli.normalize._load", return_value={}):
        with pytest.raises(SystemExit):
            cmd_normalize(args)


def test_cmd_normalize_single_prd_no_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-001")
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id="PRD-001", all=False, check=False
    )
    with (
        patch("darkfactory.cli.normalize._load", return_value={"PRD-001": prd}),
        patch("darkfactory.cli.normalize._normalize_prd", return_value=False),
    ):
        result = cmd_normalize(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_cmd_normalize_single_prd_with_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-001")
    args = argparse.Namespace(
        data_dir=tmp_path, prd_id="PRD-001", all=False, check=False
    )
    with (
        patch("darkfactory.cli.normalize._load", return_value={"PRD-001": prd}),
        patch("darkfactory.cli.normalize._normalize_prd", return_value=True),
    ):
        result = cmd_normalize(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "normalized: PRD-001" in captured.out


def test_cmd_normalize_check_mode_no_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-001")
    args = argparse.Namespace(data_dir=tmp_path, prd_id="PRD-001", all=False, check=True)
    with (
        patch("darkfactory.cli.normalize._load", return_value={"PRD-001": prd}),
        patch("darkfactory.cli.normalize._normalize_prd", return_value=False),
    ):
        result = cmd_normalize(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "already canonical" in captured.out


def test_cmd_normalize_check_mode_with_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-001")
    args = argparse.Namespace(data_dir=tmp_path, prd_id="PRD-001", all=False, check=True)
    with (
        patch("darkfactory.cli.normalize._load", return_value={"PRD-001": prd}),
        patch("darkfactory.cli.normalize._normalize_prd", return_value=True),
    ):
        result = cmd_normalize(args)
    assert result == 1
    captured = capsys.readouterr()
    assert "would be changed" in captured.err


def test_cmd_normalize_all_flag(tmp_path: Path) -> None:
    prd1 = _make_prd("PRD-001")
    prd2 = _make_prd("PRD-002")
    prds = {"PRD-001": prd1, "PRD-002": prd2}
    args = argparse.Namespace(data_dir=tmp_path, prd_id=None, all=True, check=False)
    with (
        patch("darkfactory.cli.normalize._load", return_value=prds),
        patch("darkfactory.cli.normalize._normalize_prd", return_value=False),
    ):
        result = cmd_normalize(args)
    assert result == 0
