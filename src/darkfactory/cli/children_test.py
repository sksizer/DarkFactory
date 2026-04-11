"""Tests for cli/children.py — cmd_children output formatting."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.children import cmd_children


def _make_args(data_dir: Path, prd_id: str) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
    ns.prd_id = prd_id
    return ns


def _make_prd(
    *,
    id: str,
    title: str = "A task",
    status: str = "ready",
    kind: str = "task",
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.title = title
    prd.status = status
    prd.kind = kind
    return prd


def test_cmd_children_with_children(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parent = _make_prd(id="PRD-001", title="Parent task")
    child1 = _make_prd(id="PRD-001.1", title="First child", kind="task")
    child2 = _make_prd(id="PRD-001.2", title="Second child", kind="task")
    prds = {"PRD-001": parent, "PRD-001.1": child1, "PRD-001.2": child2}
    args = _make_args(tmp_path, "PRD-001")

    with (
        patch("darkfactory.cli.children._load", return_value=prds),
        patch("darkfactory.containment.children", return_value=[child1, child2]),
    ):
        rc = cmd_children(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-001.1" in out
    assert "PRD-001.2" in out
    assert "First child" in out
    assert "Second child" in out


def test_cmd_children_no_children(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-002", title="Leaf task")
    prds = {"PRD-002": prd}
    args = _make_args(tmp_path, "PRD-002")

    with (
        patch("darkfactory.cli.children._load", return_value=prds),
        patch("darkfactory.containment.children", return_value=[]),
    ):
        rc = cmd_children(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "(no children)" in out


def test_cmd_children_unknown_prd_id(tmp_path: Path) -> None:
    prds = {"PRD-001": _make_prd(id="PRD-001")}
    args = _make_args(tmp_path, "PRD-999")

    with patch("darkfactory.cli.children._load", return_value=prds):
        with pytest.raises(SystemExit, match="unknown PRD id"):
            cmd_children(args)
