"""Tests for cli/status.py — cmd_status output formatting and filtering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.status import cmd_status


def _make_args(prd_dir: Path, *, json_output: bool = False) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.prd_dir = prd_dir
    ns.json = json_output
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


# ---------- JSON output ----------


def test_cmd_status_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", status="ready")
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path, json_output=True)

    with (
        patch("darkfactory.cli.status._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.containment.is_runnable", return_value=True),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 1
    assert out["actionable"] == 1
    assert out["runnable"] == 1
    assert len(out["next"]) == 1
    assert out["next"][0]["id"] == "PRD-001"


def test_cmd_status_json_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path, json_output=True)

    with (
        patch("darkfactory.cli.status._load", return_value={}),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 0
    assert out["runnable"] == 0
    assert out["next"] == []


# ---------- Text output ----------


def test_cmd_status_text_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", status="ready")
    prds = {"PRD-001": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.status._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.containment.is_runnable", return_value=True),
        patch(
            "darkfactory.cli.status._find_repo_root", side_effect=SystemExit("no git")
        ),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "PRDs — 1 total" in out
    assert "ready" in out


def test_cmd_status_text_no_runnable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-002", status="blocked")
    prds = {"PRD-002": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.status._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=False),
        patch("darkfactory.containment.is_runnable", return_value=False),
        patch(
            "darkfactory.cli.status._find_repo_root", side_effect=SystemExit("no git")
        ),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "runnable: 0" in out
    assert "Next runnable" not in out


def test_cmd_status_text_shows_next_runnable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-003", title="Do the thing", status="ready")
    prds = {"PRD-003": prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.status._load", return_value=prds),
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.containment.is_runnable", return_value=True),
        patch(
            "darkfactory.cli.status._find_repo_root", side_effect=SystemExit("no git")
        ),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Next runnable" in out
    assert "PRD-003" in out
    assert "Do the thing" in out


# ---------- Stale worktrees notice ----------


def test_cmd_status_stale_worktrees_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = MagicMock()
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.status._load", return_value={}),
        patch("darkfactory.cli.status._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.status.find_stale_worktrees", return_value=[stale]),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "worktrees for merged PRDs" in out


def test_cmd_status_stale_worktrees_suppressed_when_no_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.status._load", return_value={}),
        patch(
            "darkfactory.cli.status._find_repo_root", side_effect=SystemExit("no git")
        ),
    ):
        rc = cmd_status(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "worktrees" not in out
