"""Tests for cli/assign_cmd.py — cmd_assign output and write behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.assign_cmd import cmd_assign


def _make_args(
    prd_dir: Path,
    workflows_dir: Path,
    *,
    json_output: bool = False,
    write: bool = False,
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.prd_dir = prd_dir
    ns.workflows_dir = workflows_dir
    ns.json = json_output
    ns.write = write
    return ns


def _make_prd(id: str, workflow: str | None = None) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.workflow = workflow
    return prd


def _make_workflow(name: str) -> MagicMock:
    wf = MagicMock()
    wf.name = name
    return wf


# ---------- empty workflows ----------


def test_cmd_assign_no_workflows_human(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path, tmp_path)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={}),
        patch("darkfactory.cli.assign_cmd._load_workflows_or_fail", return_value={}),
    ):
        result = cmd_assign(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "PRD" in out
    assert "Workflow" in out


def test_cmd_assign_no_workflows_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path, tmp_path, json_output=True)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={}),
        patch("darkfactory.cli.assign_cmd._load_workflows_or_fail", return_value={}),
    ):
        result = cmd_assign(args)
    out = capsys.readouterr().out
    assert result == 0
    assert json.loads(out) == []


# ---------- assign_all raises KeyError ----------


def test_cmd_assign_key_error_raises_system_exit(tmp_path: Path) -> None:
    prd = _make_prd("PRD-1")
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            side_effect=KeyError("no match"),
        ),
        pytest.raises(SystemExit),
    ):
        cmd_assign(args)


# ---------- human-readable output ----------


def test_cmd_assign_human_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-1", workflow=None)
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            return_value={"PRD-1": wf},
        ),
    ):
        result = cmd_assign(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "PRD-1" in out
    assert "default" in out
    assert "predicate" in out


def test_cmd_assign_explicit_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-1", workflow="default")
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            return_value={"PRD-1": wf},
        ),
    ):
        result = cmd_assign(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "explicit" in out


# ---------- JSON output ----------


def test_cmd_assign_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-1", workflow=None)
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path, json_output=True)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            return_value={"PRD-1": wf},
        ),
    ):
        result = cmd_assign(args)
    out = capsys.readouterr().out
    assert result == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["id"] == "PRD-1"
    assert data[0]["workflow"] == "default"
    assert data[0]["explicit"] is False


# ---------- --write flag ----------


def test_cmd_assign_write_persists_unassigned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-1", workflow=None)
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path, write=True)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            return_value={"PRD-1": wf},
        ),
        patch("darkfactory.cli.assign_cmd.set_workflow") as mock_set,
    ):
        result = cmd_assign(args)
    assert result == 0
    mock_set.assert_called_once_with(prd, "default")
    out = capsys.readouterr().out
    assert "Persisted 1 workflow" in out


def test_cmd_assign_write_skips_already_assigned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd("PRD-1", workflow="default")
    wf = _make_workflow("default")
    args = _make_args(tmp_path, tmp_path, write=True)
    with (
        patch("darkfactory.cli.assign_cmd._load", return_value={"PRD-1": prd}),
        patch(
            "darkfactory.cli.assign_cmd._load_workflows_or_fail",
            return_value={"default": wf},
        ),
        patch(
            "darkfactory.cli.assign_cmd.assign.assign_all",
            return_value={"PRD-1": wf},
        ),
        patch("darkfactory.cli.assign_cmd.set_workflow") as mock_set,
    ):
        result = cmd_assign(args)
    assert result == 0
    mock_set.assert_not_called()
    out = capsys.readouterr().out
    assert "Persisted 0 workflow" in out
