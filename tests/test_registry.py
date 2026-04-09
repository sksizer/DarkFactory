"""Tests for the cascade workflow registry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.registry import (
    InvalidWorkflow,
    WorkflowNameCollision,
    _validate_workflow,
    build_workflow_registry,
)
from darkfactory.workflow import Workflow


# ---------- helpers ----------


def _make_workflow(name: str) -> Workflow:
    """Create a minimal valid Workflow for tests."""
    return Workflow(
        name=name,
        applies_to=lambda prd, prds: True,
        tasks=[],
    )


def _write_workflow_file(parent: Path, name: str, *, body: str | None = None) -> None:
    """Write a workflow.py under parent/<name>/workflow.py."""
    subdir = parent / name
    subdir.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = f"""from darkfactory.workflow import Workflow
workflow = Workflow(name={name!r}, applies_to=lambda prd, prds: True, tasks=[])
"""
    (subdir / "workflow.py").write_text(body)


# ---------- _validate_workflow ----------


def test_validate_workflow_passes_valid() -> None:
    wf = _make_workflow("good")
    _validate_workflow(wf, "built-in", Path("<package>/good"))


def test_validate_workflow_missing_name() -> None:
    wf = _make_workflow("x")
    object.__setattr__(wf, "name", "")
    with pytest.raises(InvalidWorkflow) as exc_info:
        _validate_workflow(wf, "built-in", Path("<package>/x"))
    assert "name" in str(exc_info.value)
    assert "built-in" in str(exc_info.value)


def test_validate_workflow_bad_tasks_type() -> None:
    wf = _make_workflow("x")
    object.__setattr__(wf, "tasks", "not-a-list")
    with pytest.raises(InvalidWorkflow) as exc_info:
        _validate_workflow(wf, "user", Path("/home/.config/darkfactory/workflows/x"))
    assert "tasks" in str(exc_info.value)
    assert "user" in str(exc_info.value)


def test_validate_workflow_non_callable_applies_to() -> None:
    wf = _make_workflow("x")
    object.__setattr__(wf, "applies_to", "not-callable")
    with pytest.raises(InvalidWorkflow) as exc_info:
        _validate_workflow(wf, "project", Path("/proj/.darkfactory/workflows/x"))
    assert "applies_to" in str(exc_info.value)
    assert "project" in str(exc_info.value)


# ---------- error message format ----------


def test_workflow_name_collision_message() -> None:
    exc = WorkflowNameCollision(
        "alpha",
        [
            ("built-in", Path("<package>/alpha")),
            ("user", Path("/home/.config/darkfactory/workflows/alpha")),
        ],
    )
    msg = str(exc)
    assert "alpha" in msg
    assert "multiple layers" in msg
    assert "Rename or delete" in msg


def test_invalid_workflow_message() -> None:
    exc = InvalidWorkflow(
        "user", Path("/home/.config/darkfactory/workflows/bad"), "missing name"
    )
    msg = str(exc)
    assert "user" in msg
    assert "missing name" in msg
    assert "failed validation" in msg


# ---------- build_workflow_registry — layer combinations ----------


def _empty_user_dir(tmp_path: Path) -> Path:
    """Return a tmp dir to use as user workflows dir (empty)."""
    d = tmp_path / "user_workflows"
    d.mkdir()
    return d


def test_builtin_only(real_builtin_workflows: None, tmp_path: Path) -> None:
    """Built-in workflows are discovered when no user/project dirs exist."""
    user_dir = tmp_path / "user_workflows"
    # user_dir does NOT exist — the registry should still return built-ins
    with patch("darkfactory.registry.user_workflows_dir", return_value=user_dir):
        result = build_workflow_registry(project_dir=None)
    assert len(result) > 0
    assert "default" in result
    for wf in result.values():
        assert isinstance(wf, Workflow)


def test_user_only(tmp_path: Path) -> None:
    """User-only workflows (no built-ins, no project) discovered correctly."""
    user_dir = tmp_path / "user_workflows"
    _write_workflow_file(user_dir, "myworkflow")

    empty_project_dir = tmp_path / "project"
    empty_project_dir.mkdir()

    # Patch get_builtin_workflows to return nothing so we isolate user layer
    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        result = build_workflow_registry(project_dir=empty_project_dir)

    assert "myworkflow" in result
    assert isinstance(result["myworkflow"], Workflow)


def test_project_only(tmp_path: Path) -> None:
    """Project-only workflows discovered correctly."""
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(project_dir / "workflows", "projworkflow")

    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        result = build_workflow_registry(project_dir=project_dir)

    assert "projworkflow" in result
    assert isinstance(result["projworkflow"], Workflow)


def test_builtin_and_project_no_collision(tmp_path: Path) -> None:
    """Built-in + project with no collision — all merged."""
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(project_dir / "workflows", "custom")

    builtin_wf = _make_workflow("builtin_one")
    with (
        patch(
            "darkfactory.registry.get_builtin_workflows",
            return_value={"builtin_one": builtin_wf},
        ),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        result = build_workflow_registry(project_dir=project_dir)

    assert "builtin_one" in result
    assert "custom" in result


def test_collision_builtin_and_user(tmp_path: Path) -> None:
    """Collision between built-in and user raises WorkflowNameCollision."""
    user_dir = tmp_path / "user_workflows"
    _write_workflow_file(user_dir, "shared")

    builtin_wf = _make_workflow("shared")
    with (
        patch(
            "darkfactory.registry.get_builtin_workflows",
            return_value={"shared": builtin_wf},
        ),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(WorkflowNameCollision) as exc_info:
            build_workflow_registry(project_dir=None)

    assert "shared" in str(exc_info.value)
    assert "built-in" in str(exc_info.value)
    assert "user" in str(exc_info.value)


def test_collision_builtin_and_project(tmp_path: Path) -> None:
    """Collision between built-in and project raises WorkflowNameCollision."""
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(project_dir / "workflows", "shared")

    builtin_wf = _make_workflow("shared")
    with (
        patch(
            "darkfactory.registry.get_builtin_workflows",
            return_value={"shared": builtin_wf},
        ),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(WorkflowNameCollision) as exc_info:
            build_workflow_registry(project_dir=project_dir)

    assert "shared" in str(exc_info.value)
    assert "built-in" in str(exc_info.value)
    assert "project" in str(exc_info.value)


def test_collision_user_and_project(tmp_path: Path) -> None:
    """Collision between user and project raises WorkflowNameCollision."""
    user_dir = tmp_path / "user_workflows"
    _write_workflow_file(user_dir, "shared")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(project_dir / "workflows", "shared")

    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(WorkflowNameCollision) as exc_info:
            build_workflow_registry(project_dir=project_dir)

    assert "shared" in str(exc_info.value)
    assert "user" in str(exc_info.value)
    assert "project" in str(exc_info.value)


# ---------- invalid workflows in each layer ----------


def test_invalid_workflow_in_builtin_layer(tmp_path: Path) -> None:
    """InvalidWorkflow raised for a built-in that fails validation."""
    bad_wf = _make_workflow("bad")
    object.__setattr__(bad_wf, "name", "")  # missing name

    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    with (
        patch(
            "darkfactory.registry.get_builtin_workflows", return_value={"bad": bad_wf}
        ),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(InvalidWorkflow) as exc_info:
            build_workflow_registry(project_dir=None)

    err = str(exc_info.value)
    assert "built-in" in err
    assert "name" in err


def test_invalid_workflow_in_user_layer_bad_tasks(tmp_path: Path) -> None:
    """InvalidWorkflow raised for a user workflow with wrong tasks type."""
    user_dir = tmp_path / "user_workflows"
    _write_workflow_file(
        user_dir,
        "baduserworkflow",
        body=(
            "from darkfactory.workflow import Workflow\n"
            "workflow = Workflow(name='baduserworkflow', applies_to=lambda prd, prds: True, tasks=[])\n"
            "workflow.tasks = 'not-a-list'\n"
        ),
    )

    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(InvalidWorkflow) as exc_info:
            build_workflow_registry(project_dir=None)

    err = str(exc_info.value)
    assert "user" in err
    assert "tasks" in err


def test_invalid_workflow_in_project_layer_non_callable_applies_to(
    tmp_path: Path,
) -> None:
    """InvalidWorkflow raised for a project workflow with non-callable applies_to."""
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(
        project_dir / "workflows",
        "badprojworkflow",
        body=(
            "from darkfactory.workflow import Workflow\n"
            "workflow = Workflow(name='badprojworkflow', applies_to=lambda prd, prds: True, tasks=[])\n"
            "workflow.applies_to = 'not-callable'\n"
        ),
    )

    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(InvalidWorkflow) as exc_info:
            build_workflow_registry(project_dir=project_dir)

    err = str(exc_info.value)
    assert "project" in err
    assert "applies_to" in err


# ---------- error messages include layer, path, and reason ----------


def test_collision_error_includes_all_paths(tmp_path: Path) -> None:
    """WorkflowNameCollision error contains both conflicting paths."""
    user_dir = tmp_path / "user_workflows"
    _write_workflow_file(user_dir, "clash")

    builtin_wf = _make_workflow("clash")
    with (
        patch(
            "darkfactory.registry.get_builtin_workflows",
            return_value={"clash": builtin_wf},
        ),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(WorkflowNameCollision) as exc_info:
            build_workflow_registry(project_dir=None)

    err = str(exc_info.value)
    assert "<package>" in err
    assert str(user_dir) in err


def test_invalid_workflow_error_includes_layer_path_reason(tmp_path: Path) -> None:
    """InvalidWorkflow error contains layer, path, and specific reason."""
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir()

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_workflow_file(
        project_dir / "workflows",
        "brokenworkflow",
        body=(
            "from darkfactory.workflow import Workflow\n"
            "workflow = Workflow(name='brokenworkflow', applies_to=lambda prd, prds: True, tasks=[])\n"
            "workflow.applies_to = 42\n"
        ),
    )

    with (
        patch("darkfactory.registry.get_builtin_workflows", return_value={}),
        patch("darkfactory.registry.user_workflows_dir", return_value=user_dir),
    ):
        with pytest.raises(InvalidWorkflow) as exc_info:
            build_workflow_registry(project_dir=project_dir)

    err = str(exc_info.value)
    assert "project" in err
    assert "brokenworkflow" in err
    assert "applies_to" in err
