"""Tests for the planning-review workflow.

Covers:
- The planning-review workflow loads via the standard loader
- The applies_to predicate routes correctly for partially-decomposed epics
- is_partially_decomposed behaviour
- Model pinning to opus with model_from_capability=False
- Routing: partially-decomposed -> planning-review, undecomposed -> planning,
  decomposition: complete -> neither
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from darkfactory.cli import main
from darkfactory.containment import is_partially_decomposed
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


def _write_prd_with_decomposition(
    dir_path: Path,
    prd_id: str,
    slug: str,
    decomposition: str,
    **kwargs: object,
) -> Path:
    """Write a PRD file with an extra ``decomposition`` frontmatter field."""
    # Write a normal PRD first, then inject the decomposition field.
    path = write_prd(dir_path, prd_id, slug, **kwargs)  # type: ignore[arg-type]
    text = path.read_text(encoding="utf-8")
    # Insert the decomposition field just before the closing ---
    text = text.replace(
        "\ntags: []\n---",
        f"\ntags: []\ndecomposition: {decomposition}\n---",
    )
    path.write_text(text, encoding="utf-8")
    return path


# ---------- is_partially_decomposed ----------


def test_partially_decomposed_false_for_zero_children(tmp_data_dir: Path) -> None:
    """An epic with no children is not partially decomposed."""
    write_prd(tmp_data_dir / "prds", "PRD-100", "epic", kind="epic", status="ready")
    prds = load_all(tmp_data_dir)
    assert not is_partially_decomposed(prds["PRD-100"], prds)


def test_partially_decomposed_true_for_has_children(tmp_data_dir: Path) -> None:
    """An epic with task children and no decomposition flag is partially decomposed."""
    write_prd(tmp_data_dir / "prds", "PRD-100", "epic", kind="epic", status="ready")
    write_prd(
        tmp_data_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100"
    )
    prds = load_all(tmp_data_dir)
    assert is_partially_decomposed(prds["PRD-100"], prds)


def test_partially_decomposed_false_for_complete_flag(tmp_data_dir: Path) -> None:
    """An epic with decomposition: complete is not partially decomposed."""
    _write_prd_with_decomposition(
        tmp_data_dir / "prds",
        "PRD-100",
        "epic",
        "complete",
        kind="epic",
        status="ready",
    )
    write_prd(
        tmp_data_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100"
    )
    prds = load_all(tmp_data_dir)
    assert not is_partially_decomposed(prds["PRD-100"], prds)


# ---------- loader ----------


def test_planning_review_workflow_loads() -> None:
    """The planning-review workflow is discovered by the loader."""
    workflows = load_workflows()
    assert "planning-review" in workflows


def test_planning_review_workflow_priority() -> None:
    """Priority is 6 -- above initial planning (5)."""
    workflows = load_workflows()
    assert workflows["planning-review"].priority == 6


def test_planning_review_workflow_description() -> None:
    """Description is non-empty and mentions review."""
    workflows = load_workflows()
    assert "review" in workflows["planning-review"].description.lower()


# ---------- applies_to predicate ----------


def test_applies_to_partially_decomposed_epic(tmp_data_dir: Path) -> None:
    """A partially-decomposed epic in ready status matches planning-review."""
    write_prd(tmp_data_dir / "prds", "PRD-100", "epic", kind="epic", status="ready")
    write_prd(
        tmp_data_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100"
    )
    prds = load_all(tmp_data_dir)
    workflows = load_workflows()
    assert workflows["planning-review"].applies_to(prds["PRD-100"], prds)


def test_applies_to_partially_decomposed_in_progress(tmp_data_dir: Path) -> None:
    """A partially-decomposed epic in in-progress status matches planning-review."""
    write_prd(
        tmp_data_dir / "prds", "PRD-100", "epic", kind="epic", status="in-progress"
    )
    write_prd(
        tmp_data_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100"
    )
    prds = load_all(tmp_data_dir)
    workflows = load_workflows()
    assert workflows["planning-review"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_undecomposed_epic(tmp_data_dir: Path) -> None:
    """An epic with zero children should NOT match planning-review."""
    write_prd(tmp_data_dir / "prds", "PRD-100", "epic", kind="epic", status="ready")
    prds = load_all(tmp_data_dir)
    workflows = load_workflows()
    assert not workflows["planning-review"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_complete_epic(tmp_data_dir: Path) -> None:
    """An epic with decomposition: complete should NOT match planning-review."""
    _write_prd_with_decomposition(
        tmp_data_dir / "prds",
        "PRD-100",
        "epic",
        "complete",
        kind="epic",
        status="ready",
    )
    write_prd(
        tmp_data_dir / "prds", "PRD-100.1", "child-task", kind="task", parent="PRD-100"
    )
    prds = load_all(tmp_data_dir)
    workflows = load_workflows()
    assert not workflows["planning-review"].applies_to(prds["PRD-100"], prds)


def test_does_not_apply_to_task(tmp_data_dir: Path) -> None:
    """A task PRD does not match planning-review."""
    write_prd(
        tmp_data_dir / "prds", "PRD-100", "leaf-task", kind="task", status="ready"
    )
    prds = load_all(tmp_data_dir)
    workflows = load_workflows()
    assert not workflows["planning-review"].applies_to(prds["PRD-100"], prds)


# ---------- agent task properties ----------


def test_agent_task_model_pinned_to_opus() -> None:
    """The review-and-extend AgentTask is pinned to opus."""
    from darkfactory.workflow import AgentTask

    workflows = load_workflows()
    planning_review = workflows["planning-review"]
    agent_tasks = [t for t in planning_review.tasks if isinstance(t, AgentTask)]
    assert len(agent_tasks) == 1
    agent = agent_tasks[0]
    assert agent.model == "opus"
    assert agent.model_from_capability is False


def test_agent_task_has_write_but_not_edit() -> None:
    """The review AgentTask includes Write but NOT Edit."""
    from darkfactory.workflow import AgentTask

    workflows = load_workflows()
    planning_review = workflows["planning-review"]
    agent_tasks = [t for t in planning_review.tasks if isinstance(t, AgentTask)]
    agent = agent_tasks[0]
    assert "Write" in agent.tools
    assert "Edit" not in agent.tools


# ---------- CLI integration ----------


def test_list_workflows_shows_planning_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd list-workflows includes the planning-review workflow at priority 6."""
    prd_dir, _workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-001", "placeholder")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "list-workflows",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "planning-review" in out
    assert "priority=6" in out


def test_plan_routes_partial_epic_to_planning_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan on a partially-decomposed epic routes to planning-review with opus."""
    prd_dir, _workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-100", "big-epic", kind="epic", status="ready")
    write_prd(prd_dir, "PRD-100.1", "child-task", kind="task", parent="PRD-100")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "planning-review" in out
    assert "opus" in out


def test_plan_routes_undecomposed_to_planning_not_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan on an undecomposed epic routes to planning, not planning-review."""
    prd_dir, _workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-100", "big-epic", kind="epic", status="ready")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    # Should route to initial planning, not planning-review
    assert "planning" in out
    assert "planning-review" not in out


def test_plan_complete_epic_routes_to_neither(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan on an epic with decomposition: complete routes to default."""
    prd_dir, _workflows_dir = _setup_project(tmp_path)
    _write_prd_with_decomposition(
        prd_dir, "PRD-100", "big-epic", "complete", kind="epic", status="ready"
    )
    write_prd(prd_dir, "PRD-100.1", "child-task", kind="task", parent="PRD-100")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--json",
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # Should route to default -- neither planning nor planning-review
    assert payload["workflow"]["name"] not in ("planning", "planning-review")


def test_plan_json_routes_partial_epic_to_planning_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd plan --json on a partially-decomposed epic shows planning-review with opus."""
    prd_dir, _workflows_dir = _setup_project(tmp_path)
    write_prd(prd_dir, "PRD-100", "big-epic", kind="epic", status="ready")
    write_prd(prd_dir, "PRD-100.1", "child-task", kind="task", parent="PRD-100")

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--json",
            "plan",
            "PRD-100",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["name"] == "planning-review"
    agent_tasks = [t for t in payload["tasks"] if "agent:" in t]
    assert len(agent_tasks) == 1
    assert "model=opus" in agent_tasks[0]
