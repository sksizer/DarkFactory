"""Tests for cli/plan.py — _describe_task, _resolve_base_ref, _check_runnable, cmd_plan."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli._shared import _check_runnable, _resolve_base_ref
from darkfactory.cli.plan import (
    _describe_task,
    cmd_plan,
)


# ---------- helpers ----------


def _make_prd(
    *,
    id: str = "PRD-001",
    title: str = "A task",
    status: str = "ready",
    priority: str = "medium",
    effort: str = "s",
    kind: str = "task",
    capability: str = "simple",
    depends_on: list[str] | None = None,
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.title = title
    prd.status = status
    prd.priority = priority
    prd.effort = effort
    prd.kind = kind
    prd.capability = capability
    prd.depends_on = depends_on or []
    return prd


def _make_plan_args(
    data_dir: Path,
    *,
    prd_id: str = "PRD-001",
    workflows_dir: Path | None = None,
    workflow: str | None = None,
    base: str | None = None,
    model: str | None = None,
    json_output: bool = False,
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
    ns.workflows_dir = workflows_dir or data_dir
    ns.prd_id = prd_id
    ns.workflow = workflow
    ns.base = base
    ns.model = model
    ns.json = json_output
    return ns


# ---------- _describe_task ----------


def test_describe_task_builtin_no_kwargs() -> None:
    from darkfactory.workflow import BuiltIn

    task = BuiltIn(name="reconcile-status", kwargs={})
    result = _describe_task(task, MagicMock(), None)
    assert result == "builtin: reconcile-status"


def test_describe_task_builtin_with_kwargs() -> None:
    from darkfactory.workflow import BuiltIn

    task = BuiltIn(name="open-pr", kwargs={"draft": True})
    result = _describe_task(task, MagicMock(), None)
    assert "builtin: open-pr" in result
    assert "draft=True" in result


def test_describe_task_agent_task() -> None:
    from darkfactory.workflow import AgentTask

    task = AgentTask(
        name="implement",
        prompts=["prd-work"],
        tools=["Read", "Edit", "Bash"],
        retries=2,
    )
    prd = _make_prd(capability="simple")
    with patch("darkfactory.cli.plan._pick_model", return_value="claude-haiku"):
        result = _describe_task(task, prd, None)
    assert "agent: implement" in result
    assert "model=claude-haiku" in result
    assert "prompts=prd-work" in result
    assert "tools=3" in result
    assert "retries=2" in result


def test_describe_task_shell_task() -> None:
    from darkfactory.workflow import ShellTask

    task = ShellTask(name="run-tests", cmd="just test", on_failure="fail")
    result = _describe_task(task, MagicMock(), None)
    assert result == "shell: run-tests (fail) -> just test"


def test_describe_task_unknown_type() -> None:
    class WeirdTask:
        pass

    result = _describe_task(WeirdTask(), MagicMock(), None)  # type: ignore[arg-type]
    assert "unknown task type" in result
    assert "WeirdTask" in result


# ---------- _resolve_base_ref ----------


def test_resolve_base_ref_explicit(tmp_path: Path) -> None:
    result = _resolve_base_ref("my-branch", tmp_path)
    assert result == "my-branch"


def test_resolve_base_ref_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DARKFACTORY_BASE_REF", "env-branch")
    result = _resolve_base_ref(None, tmp_path)
    assert result == "env-branch"


def test_resolve_base_ref_main_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DARKFACTORY_BASE_REF", raising=False)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _resolve_base_ref(None, tmp_path)
    assert result == "main"


def test_resolve_base_ref_master_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DARKFACTORY_BASE_REF", raising=False)

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        # cmd contains refs/heads/main or refs/heads/master as an element
        if any("refs/heads/main" in c for c in cmd):
            return MagicMock(returncode=1)
        if any("refs/heads/master" in c for c in cmd):
            return MagicMock(returncode=0)
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=side_effect):
        result = _resolve_base_ref(None, tmp_path)
    assert result == "master"


def test_resolve_base_ref_origin_head_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DARKFACTORY_BASE_REF", raising=False)

    call_count = 0

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        # First two calls are rev-parse for main/master — both fail.
        if "rev-parse" in cmd:
            return MagicMock(returncode=1)
        # Third call is symbolic-ref — succeeds.
        if "symbolic-ref" in cmd:
            return MagicMock(returncode=0, stdout="refs/remotes/origin/develop\n")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=side_effect):
        result = _resolve_base_ref(None, tmp_path)
    assert result == "develop"


def test_resolve_base_ref_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DARKFACTORY_BASE_REF", raising=False)

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        if "rev-parse" in cmd:
            return MagicMock(returncode=1)
        raise subprocess.CalledProcessError(1, cmd)

    with patch("subprocess.run", side_effect=side_effect):
        result = _resolve_base_ref(None, tmp_path)
    assert result == "main"


# ---------- _check_runnable ----------


def test_check_runnable_done() -> None:
    prd = _make_prd(status="done")
    result = _check_runnable(prd, {"PRD-001": prd})
    assert result is not None
    assert "already done" in result


def test_check_runnable_cancelled() -> None:
    prd = _make_prd(status="cancelled")
    result = _check_runnable(prd, {"PRD-001": prd})
    assert result is not None
    assert "cancelled" in result


def test_check_runnable_not_actionable_missing_deps() -> None:
    prd = _make_prd(status="ready", id="PRD-002")
    with (
        patch("darkfactory.graph.is_actionable", return_value=False),
        patch("darkfactory.graph.missing_deps", return_value=["PRD-999"]),
    ):
        result = _check_runnable(prd, {"PRD-002": prd})
    assert result is not None
    assert "missing PRDs" in result
    assert "PRD-999" in result


def test_check_runnable_not_actionable_unfinished_deps() -> None:
    dep = _make_prd(id="PRD-001", status="in-progress")
    prd = _make_prd(id="PRD-002", status="ready", depends_on=["PRD-001"])
    prds = {"PRD-001": dep, "PRD-002": prd}
    with (
        patch("darkfactory.graph.is_actionable", return_value=False),
        patch("darkfactory.graph.missing_deps", return_value=[]),
    ):
        result = _check_runnable(prd, prds)  # type: ignore[arg-type]
    assert result is not None
    assert "unfinished dependencies" in result


def test_check_runnable_epic_not_leaf() -> None:
    prd = _make_prd(status="ready", kind="epic")
    prds = {"PRD-001": prd}
    with (
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.containment.is_runnable", return_value=False),
    ):
        result = _check_runnable(prd, prds)  # type: ignore[arg-type]
    assert result is not None
    assert "epic/feature with children" in result


def test_check_runnable_ok() -> None:
    prd = _make_prd(status="ready")
    prds = {"PRD-001": prd}
    with (
        patch("darkfactory.graph.is_actionable", return_value=True),
        patch("darkfactory.containment.is_runnable", return_value=True),
    ):
        result = _check_runnable(prd, prds)  # type: ignore[arg-type]
    assert result is None


# ---------- cmd_plan ----------


def _make_workflow(
    name: str = "default",
    tasks: list[Any] | None = None,
    description: str = "",
    template_name: str | None = None,
    priority: int = 0,
) -> MagicMock:
    wf = MagicMock()
    wf.name = name
    wf.description = description
    wf.template_name = template_name
    wf.priority = priority
    wf.tasks = tasks or []
    return wf


def test_cmd_plan_unknown_prd(tmp_path: Path) -> None:
    args = _make_plan_args(tmp_path, prd_id="PRD-999")
    with (
        patch("darkfactory.cli.plan._load", return_value={}),
        pytest.raises(SystemExit, match="unknown PRD id"),
    ):
        cmd_plan(args)


def test_cmd_plan_text_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", title="My Task")
    workflow = _make_workflow(name="prd-task")
    args = _make_plan_args(tmp_path, prd_id="PRD-001")

    with (
        patch("darkfactory.cli.plan._load", return_value={"PRD-001": prd}),
        patch(
            "darkfactory.cli.plan._load_workflows_or_fail",
            return_value={"prd-task": workflow},
        ),
        patch("darkfactory.assign.assign_workflow", return_value=workflow),
        patch(
            "darkfactory.cli.plan._compute_branch_name",
            return_value="prd/PRD-001-my-task",
        ),
        patch("darkfactory.cli.plan._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.plan._resolve_base_ref", return_value="main"),
        patch("darkfactory.cli.plan._check_runnable", return_value=None),
        patch("darkfactory.cli.plan.capability_to_model", return_value="claude-haiku"),
    ):
        rc = cmd_plan(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Plan for PRD-001" in out
    assert "My Task" in out
    assert "prd/PRD-001-my-task" in out
    assert "main" in out


def test_cmd_plan_text_shows_runnable_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", status="done")
    workflow = _make_workflow(name="prd-task")
    args = _make_plan_args(tmp_path, prd_id="PRD-001")

    with (
        patch("darkfactory.cli.plan._load", return_value={"PRD-001": prd}),
        patch(
            "darkfactory.cli.plan._load_workflows_or_fail",
            return_value={"prd-task": workflow},
        ),
        patch("darkfactory.assign.assign_workflow", return_value=workflow),
        patch(
            "darkfactory.cli.plan._compute_branch_name", return_value="prd/PRD-001-done"
        ),
        patch("darkfactory.cli.plan._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.plan._resolve_base_ref", return_value="main"),
        patch(
            "darkfactory.cli.plan._check_runnable",
            return_value="PRD-001 is already done",
        ),
        patch("darkfactory.cli.plan.capability_to_model", return_value="claude-haiku"),
    ):
        rc = cmd_plan(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "NOT RUNNABLE" in out
    assert "already done" in out


def test_cmd_plan_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", title="My Task")
    workflow = _make_workflow(name="prd-task", description="runs the PRD")
    args = _make_plan_args(tmp_path, prd_id="PRD-001", json_output=True)

    with (
        patch("darkfactory.cli.plan._load", return_value={"PRD-001": prd}),
        patch(
            "darkfactory.cli.plan._load_workflows_or_fail",
            return_value={"prd-task": workflow},
        ),
        patch("darkfactory.assign.assign_workflow", return_value=workflow),
        patch(
            "darkfactory.cli.plan._compute_branch_name",
            return_value="prd/PRD-001-my-task",
        ),
        patch("darkfactory.cli.plan._find_repo_root", return_value=tmp_path),
        patch("darkfactory.cli.plan._resolve_base_ref", return_value="main"),
        patch("darkfactory.cli.plan._check_runnable", return_value=None),
        patch("darkfactory.cli.plan.capability_to_model", return_value="claude-haiku"),
        patch("darkfactory.cli.plan._describe_task", return_value="builtin: open-pr"),
    ):
        rc = cmd_plan(args)

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["prd"]["id"] == "PRD-001"
    assert out["workflow"]["name"] == "prd-task"
    assert out["branch"] == "prd/PRD-001-my-task"
    assert out["base_ref"] == "main"
    assert out["runnable_error"] is None


def test_cmd_plan_unknown_workflow(tmp_path: Path) -> None:
    prd = _make_prd(id="PRD-001")
    args = _make_plan_args(tmp_path, prd_id="PRD-001", workflow="no-such-workflow")

    with (
        patch("darkfactory.cli.plan._load", return_value={"PRD-001": prd}),
        patch("darkfactory.cli.plan._load_workflows_or_fail", return_value={}),
        pytest.raises(SystemExit, match="unknown workflow"),
    ):
        cmd_plan(args)
