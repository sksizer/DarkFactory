"""Tests for cli/conflicts.py — cmd_conflicts output and conflict detection logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.conflicts import cmd_conflicts


def _make_args(
    data_dir: Path,
    prd_id: str = "PRD-001",
    *,
    json_output: bool = False,
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
    ns.prd_id = prd_id
    ns.json = json_output
    return ns


def _make_prd(
    *,
    id: str,
    title: str = "A task",
    impacts: list[str] | None = None,
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.title = title
    prd.impacts = impacts or []
    return prd


# ---------- unknown PRD id ----------


def test_cmd_conflicts_unknown_prd_raises(tmp_path: Path) -> None:
    args = _make_args(tmp_path, "PRD-NOPE")
    with (
        patch("darkfactory.cli.conflicts._load", return_value={}),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        pytest.raises(SystemExit, match="unknown PRD id"),
    ):
        cmd_conflicts(args)


# ---------- no effective impacts — leaf ----------


def test_cmd_conflicts_no_impacts_leaf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=[])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.conflicts.impacts.find_conflicts", return_value=[]),
        patch("darkfactory.cli.conflicts.impacts.effective_impacts", return_value=[]),
        patch("darkfactory.cli.conflicts.containment.children", return_value=[]),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "no declared impacts" in out


# ---------- no effective impacts — container with children ----------


def test_cmd_conflicts_no_impacts_container(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=[])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)
    child = MagicMock()

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.conflicts.impacts.find_conflicts", return_value=[]),
        patch("darkfactory.cli.conflicts.impacts.effective_impacts", return_value=[]),
        patch("darkfactory.cli.conflicts.containment.children", return_value=[child]),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "container" in out
    assert "no declared impacts yet" in out


# ---------- no conflicts ----------


def test_cmd_conflicts_no_conflicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.conflicts.impacts.find_conflicts", return_value=[]),
        patch(
            "darkfactory.cli.conflicts.impacts.effective_impacts",
            return_value=["src/foo.py"],
        ),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "no impact conflicts" in out
    assert "1 pattern" in out


# ---------- conflicts found — text output ----------


def test_cmd_conflicts_text_with_conflicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)
    conflict_files: set[str] = {"src/foo.py"}

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch(
            "darkfactory.cli.conflicts.impacts.find_conflicts",
            return_value=[("PRD-002", conflict_files)],
        ),
        patch(
            "darkfactory.cli.conflicts.impacts.effective_impacts",
            return_value=["src/foo.py"],
        ),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-001 conflicts:" in out
    assert "PRD-002:" in out
    assert "src/foo.py" in out


# ---------- JSON output ----------


def test_cmd_conflicts_json_no_conflicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path, json_output=True)

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.conflicts.impacts.find_conflicts", return_value=[]),
        patch(
            "darkfactory.cli.conflicts.impacts.effective_impacts",
            return_value=["src/foo.py"],
        ),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "PRD-001"
    assert data["conflicts"] == []
    assert data["effective_impacts"] == ["src/foo.py"]


def test_cmd_conflicts_json_with_conflicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path, json_output=True)
    conflict_files: set[str] = {"src/foo.py"}

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch(
            "darkfactory.cli.conflicts.impacts.find_conflicts",
            return_value=[("PRD-002", conflict_files)],
        ),
        patch(
            "darkfactory.cli.conflicts.impacts.effective_impacts",
            return_value=["src/foo.py"],
        ),
    ):
        rc = cmd_conflicts(args)

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "PRD-001"
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["id"] == "PRD-002"
    assert data["conflicts"][0]["files"] == ["src/foo.py"]


# ---------- effective_impacts raises ValueError ----------


def test_cmd_conflicts_effective_impacts_value_error(tmp_path: Path) -> None:
    prd = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.conflicts._load", return_value=prds),
        patch("darkfactory.cli.conflicts._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.conflicts.impacts.find_conflicts", return_value=[]),
        patch(
            "darkfactory.cli.conflicts.impacts.effective_impacts",
            side_effect=ValueError("bad container"),
        ),
        pytest.raises(SystemExit, match="bad container"),
    ):
        cmd_conflicts(args)
