"""Tests for the planning workflow.

Covers:
- The planning workflow loads via the standard loader
- The applies_to predicate routes correctly for epics/features/tasks
- Model pinning to opus with model_from_capability=False
- is_fully_decomposed behaviour (tested in test_containment.py too,
  but exercised here through the predicate)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from darkfactory.cli import main
from darkfactory.loader import load_workflows
from darkfactory.model import load_all

from .conftest import write_prd


pytestmark = pytest.mark.usefixtures("real_builtin_workflows")


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create .darkfactory/ layout with .git and return (prds_dir, workflows_dir)."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    df = tmp_path / ".darkfactory"
    df.mkdir()
    prds = df / "data" / "prds"
    prds.mkdir(parents=True)
    (df / "data" / "archive").mkdir()
    workflows = df / "workflows"
    workflows.mkdir()
    return prds, workflows


# ---------- loader ----------


def test_planning_workflow_loads() -> None:
    """The planning workflow is discovered by the loader."""
    workflows = load_workflows()
    assert "planning" in workflows


def test_planning_workflow_priority() -> None:
    """Priority is 5 — above default (0)."""
    workflows = load_workflows()
    assert workflows["planning"].priority == 5


def test_planning_workflow_description() -> None:
    """Description is non-empty and mentions decomposition."""
    workflows = load_workflows()
    assert "decompose" in workflows["planning"].description.lower()


# ---------- applies_to predicate ----------


def test_applies_to_undecomposed_epic(tmp_prd_dir: Path) -> None:
    """An undecomposed epic in ready status matches the planning workflow."""
    write_prd(tmp_prd_dir / "prds", "PRD-100", "big-epic", kind="epic", status="ready")
    prds = load_all(tmp_prd_dir)
    workflows = load_workflows()
    assert workflows["planning"].applies_to(prds["PRD-100"], prds)


def test_applies_to_undecomposed_feature(tmp_prd_dir: Path) -> None:
    """An undecomposed feature in ready status matches the planning workflow."""
    write_prd(tmp_prd_dir / "prds", "PRD-100", "big-feat", kind="feature", status="ready")
    prds = load_all(tmp_prd_dir)
    workflows = load_workflows()
    assert workflows["planning"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_task(tmp_prd_dir: Path) -> None:
    """A task PRD does not match the planning workflow."""
    write_prd(tmp_prd_dir / "prds", "PRD-100", "leaf-task", kind="task", status="ready")
    prds = load_all(tmp_prd_dir)
    workflows = load_workflows()
    assert not workflows["planning"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_decomposed_epic(tmp_prd_dir: Path) -> None:
    """An epic with a task descendant is already decomposed — no match."""
    write_prd(tmp_prd_dir / "prds", "PRD-100", "epic", kind="epic", status="ready")
    write_prd(tmp_prd_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100")
    prds = load_all(tmp_prd_dir)
    workflows = load_workflows()
    assert not workflows["planning"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_non_ready_epic(tmp_prd_dir: Path) -> None:
    """An epic not in ready status doesn't match."""
    write_prd(tmp_prd_dir / "prds", "PRD-100", "epic", kind="epic", status="draft")
    prds = load_all(tmp_prd_dir)
    workflows = load_workflows()
    assert not workflows["planning"].applies_to(prds["PRD-100"], prds)


# ---------- agent task properties ----------


def test_agent_task_model_pinned_to_opus() -> None:
    """The decompose AgentTask is pinned to opus."""
    from darkfactory.workflow import AgentTask

    workflows = load_workflows()
    planning = workflows["planning"]
    agent_tasks = [t for t in planning.tasks if isinstance(t, AgentTask)]
    assert len(agent_tasks) == 1
    agent = agent_tasks[0]
    assert agent.model == "opus"
    assert agent.model_from_capability is False


def test_agent_task_has_edit_tool() -> None:
    """The decompose AgentTask includes Edit in its tool allowlist."""
    from darkfactory.workflow import AgentTask

    workflows = load_workflows()
    planning = workflows["planning"]
    agent_tasks = [t for t in planning.tasks if isinstance(t, AgentTask)]
    agent = agent_tasks[0]
    assert "Edit" in agent.tools


def test_agent_task_has_write_tool() -> None:
    """The decompose AgentTask includes Write for creating PRD files."""
    from darkfactory.workflow import AgentTask

    workflows = load_workflows()
    planning = workflows["planning"]
    agent_tasks = [t for t in planning.tasks if isinstance(t, AgentTask)]
    agent = agent_tasks[0]
    assert "Write" in agent.tools


# ---------- CLI integration ----------


def test_list_workflows_shows_planning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd list-workflows includes the planning workflow at priority 5."""
    prd_dir, workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-001", "placeholder")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--workflows-dir",
            str(workflows_dir),
            "list-workflows",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "planning" in out
    assert "priority=5" in out


def test_plan_routes_epic_to_planning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan on an undecomposed epic routes to the planning workflow with opus."""
    prd_dir, workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-100", "big-epic", kind="epic", status="ready")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--workflows-dir",
            str(workflows_dir),
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "planning" in out
    assert "opus" in out


def test_plan_does_not_route_task_to_planning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan on a leaf task routes to default, not planning."""
    prd_dir, workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-001", "leaf-task", kind="task", status="ready")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--workflows-dir",
            str(workflows_dir),
            "plan",
            "PRD-001",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "default" in out
    assert "planning" not in out.split("workflow:")[0] if "workflow:" in out else True


def test_plan_json_routes_epic_to_planning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan --json on an undecomposed epic shows planning workflow with opus model."""
    prd_dir, workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-100", "big-epic", kind="epic", status="ready")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--workflows-dir",
            str(workflows_dir),
            "--json",
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["name"] == "planning"
    # The agent task should resolve to opus
    agent_tasks = [t for t in payload["tasks"] if "agent:" in t]
    assert len(agent_tasks) == 1
    assert "model=opus" in agent_tasks[0]
