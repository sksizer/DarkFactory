"""Tests for cli/orphans.py — cmd_orphans output formatting."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.orphans import cmd_orphans


def _make_args(data_dir: Path) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
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


def test_cmd_orphans_with_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root1 = _make_prd(id="PRD-001", title="Root task 1")
    root2 = _make_prd(id="PRD-002", title="Root task 2")
    prds = {"PRD-001": root1, "PRD-002": root2}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.orphans._load", return_value=prds),
        patch("darkfactory.containment.roots", return_value=[root1, root2]),
    ):
        rc = cmd_orphans(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "PRD-002" in out
    assert "Root task 1" in out
    assert "Root task 2" in out


def test_cmd_orphans_no_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prds: dict[str, MagicMock] = {}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.orphans._load", return_value=prds),
        patch("darkfactory.containment.roots", return_value=[]),
    ):
        rc = cmd_orphans(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert out == ""
