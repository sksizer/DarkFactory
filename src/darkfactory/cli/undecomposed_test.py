"""Tests for cli/undecomposed.py — cmd_undecomposed output formatting."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.undecomposed import cmd_undecomposed


def _make_args(prd_dir: Path) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.prd_dir = prd_dir
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


def test_cmd_undecomposed_with_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    epic1 = _make_prd(id="PRD-001", title="Epic 1", kind="epic")
    feature1 = _make_prd(id="PRD-002", title="Feature 1", kind="feature")
    prds = {"PRD-001": epic1, "PRD-002": feature1}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.undecomposed._load", return_value=prds),
        patch("darkfactory.containment.is_fully_decomposed", return_value=False),
    ):
        rc = cmd_undecomposed(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "PRD-002" in out
    assert "Epic 1" in out
    assert "Feature 1" in out


def test_cmd_undecomposed_no_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = _make_prd(id="PRD-003", title="Task", kind="task")
    prds = {"PRD-003": task}
    args = _make_args(tmp_path)

    with patch("darkfactory.cli.undecomposed._load", return_value=prds):
        rc = cmd_undecomposed(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "(no undecomposed epics/features)" in out
