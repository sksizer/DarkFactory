"""Tests for cli/next_cmd.py — cmd_next selection logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.next_cmd import cmd_next


def _make_args(
    data_dir: Path,
    *,
    json_output: bool = False,
    capability: str = "",
    limit: int = 10,
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
    ns.json = json_output
    ns.capability = capability
    ns.limit = limit
    return ns


def _make_prd(
    *,
    id: str,
    title: str = "A task",
    status: str = "ready",
    priority: str = "medium",
    effort: str = "s",
    kind: str = "task",
    capability: str = "simple",
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.title = title
    prd.status = status
    prd.priority = priority
    prd.effort = effort
    prd.kind = kind
    prd.capability = capability
    return prd


# ---------- selection logic ----------


def test_cmd_next_no_actionable_prints_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path)
    with (
        patch("darkfactory.cli.next_cmd._load", return_value={}),
        patch("darkfactory.graph.is_actionable", return_value=False),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "(no actionable PRDs match)" in captured.out


def test_cmd_next_filters_by_capability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_simple = _make_prd(id="PRD-001", capability="simple")
    prd_complex = _make_prd(id="PRD-002", capability="complex")
    prds = {"PRD-001": prd_simple, "PRD-002": prd_complex}
    args = _make_args(tmp_path, capability="simple")
    with (
        patch("darkfactory.cli.next_cmd._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "PRD-001" in captured.out
    assert "PRD-002" not in captured.out


def test_cmd_next_respects_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prds = {f"PRD-{i:03d}": _make_prd(id=f"PRD-{i:03d}") for i in range(1, 6)}
    args = _make_args(tmp_path, limit=2)
    with (
        patch("darkfactory.cli.next_cmd._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 2


def test_cmd_next_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", title="My task")
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path, json_output=True)
    with (
        patch("darkfactory.cli.next_cmd._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["id"] == "PRD-001"
    assert data[0]["title"] == "My task"


def test_cmd_next_excludes_non_runnable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_runnable = _make_prd(id="PRD-001")
    prd_blocked = _make_prd(id="PRD-002")
    prds = {"PRD-001": prd_runnable, "PRD-002": prd_blocked}
    args = _make_args(tmp_path)

    def fake_runnable(prd: Any, all_prds: Any) -> bool:
        return bool(prd.id == "PRD-001")

    with (
        patch("darkfactory.cli.next_cmd._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.graph._containment.is_runnable", side_effect=fake_runnable),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "PRD-001" in captured.out
    assert "PRD-002" not in captured.out


def test_cmd_next_is_actionable_filters_prds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only PRDs where is_actionable returns True should appear in output."""
    prd_a = _make_prd(id="PRD-010", title="Actionable task")
    prd_b = _make_prd(id="PRD-020", title="Blocked task")
    prd_c = _make_prd(id="PRD-030", title="Another actionable")
    prds = {"PRD-010": prd_a, "PRD-020": prd_b, "PRD-030": prd_c}
    args = _make_args(tmp_path)

    actionable_ids = {"PRD-010", "PRD-030"}

    def fake_actionable(prd: Any, all_prds: Any) -> bool:
        return bool(prd.id in actionable_ids)

    with (
        patch("darkfactory.cli.next_cmd._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", side_effect=fake_actionable),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    assert "PRD-010" in captured.out
    assert "PRD-030" in captured.out
    assert "PRD-020" not in captured.out


def test_cmd_next_json_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path, json_output=True)
    with (
        patch("darkfactory.cli.next_cmd._load", return_value={}),
        patch("darkfactory.graph.is_actionable", return_value=False),
        patch("darkfactory.graph._containment.is_runnable", return_value=True),
    ):
        result = cmd_next(args)
    assert result == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == []
