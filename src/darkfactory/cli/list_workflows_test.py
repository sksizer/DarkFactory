"""Tests for cli/list_workflows.py — cmd_list_workflows output formatting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.list_workflows import cmd_list_workflows


def _make_args(workflows_dir: Path, *, json_output: bool = False) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.workflows_dir = workflows_dir
    ns.json = json_output
    return ns


def _make_workflow(
    *,
    name: str,
    priority: int = 50,
    description: str = "",
    tasks: list[object] | None = None,
    workflow_dir: Path | None = None,
) -> MagicMock:
    wf = MagicMock()
    wf.name = name
    wf.priority = priority
    wf.description = description
    wf.tasks = tasks if tasks is not None else []
    wf.workflow_dir = workflow_dir
    return wf


# ---------- no workflows ----------


def test_cmd_list_workflows_no_workflows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _make_args(tmp_path)
    with patch(
        "darkfactory.cli.list_workflows._load_workflows_or_fail", return_value={}
    ):
        rc = cmd_list_workflows(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "(no workflows loaded)" in out


# ---------- JSON output ----------


def test_cmd_list_workflows_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wf = _make_workflow(
        name="default", priority=50, description="A workflow", tasks=[MagicMock()]
    )
    args = _make_args(tmp_path, json_output=True)
    with patch(
        "darkfactory.cli.list_workflows._load_workflows_or_fail",
        return_value={"default": wf},
    ):
        rc = cmd_list_workflows(args)
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert len(payload) == 1
    assert payload[0]["name"] == "default"
    assert payload[0]["priority"] == 50
    assert payload[0]["task_count"] == 1


def test_cmd_list_workflows_json_workflow_dir_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wf = _make_workflow(name="builtin", priority=100, workflow_dir=None)
    args = _make_args(tmp_path, json_output=True)
    with patch(
        "darkfactory.cli.list_workflows._load_workflows_or_fail",
        return_value={"builtin": wf},
    ):
        rc = cmd_list_workflows(args)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["workflow_dir"] is None


# ---------- human-readable output ----------


def test_cmd_list_workflows_human_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wf = _make_workflow(name="default", priority=50, description="Does things")
    args = _make_args(tmp_path)
    with patch(
        "darkfactory.cli.list_workflows._load_workflows_or_fail",
        return_value={"default": wf},
    ):
        rc = cmd_list_workflows(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "default" in out
    assert "priority=50" in out
    assert "Does things" in out


def test_cmd_list_workflows_sorted_by_priority_desc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wf_low = _make_workflow(name="low", priority=10)
    wf_high = _make_workflow(name="high", priority=90)
    args = _make_args(tmp_path, json_output=True)
    with patch(
        "darkfactory.cli.list_workflows._load_workflows_or_fail",
        return_value={"low": wf_low, "high": wf_high},
    ):
        rc = cmd_list_workflows(args)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "high"
    assert payload[1]["name"] == "low"
