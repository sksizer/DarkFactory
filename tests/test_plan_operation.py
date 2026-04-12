"""Tests for the plan project operation (PRD-223.6).

Covers:
- Operation loads and has accepts_target=True
- Operation is rejected without --target
- Task list is well-formed
- Operation is discoverable via prd project list
"""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.loader import load_operations
from darkfactory.project import ProjectOperation
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask


# ---------- helpers ----------


def _find_operations_dir() -> Path:
    """Return the built-in project operations directory inside the package.

    These now live at ``src/darkfactory/workflow/definitions/project/``.
    """
    here = Path(__file__).resolve().parent
    for candidate in [here.parent, here.parent.parent]:
        ops = candidate / "src" / "darkfactory" / "workflow" / "definitions" / "project"
        if ops.exists():
            return ops
    raise FileNotFoundError(
        "Could not locate workflow/definitions/project/ directory from tests/"
    )


def _setup_project(tmp_path: Path) -> Path:
    """Create .darkfactory/ layout with .git and return the prds dir."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    df = tmp_path / ".darkfactory"
    df.mkdir()
    prds = df / "data" / "prds"
    prds.mkdir(parents=True)
    (df / "data" / "archive").mkdir()
    return prds


# ---------- operation loading ----------


def test_plan_operation_loads() -> None:
    """The plan operation.py loads without errors."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    assert "plan" in operations, (
        f"'plan' not found in operations; found: {list(operations)}"
    )


def test_plan_operation_accepts_target() -> None:
    """The plan operation has accepts_target=True."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    assert op.accepts_target is True


def test_plan_operation_creates_pr() -> None:
    """The plan operation has creates_pr=True."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    assert op.creates_pr is True


def test_plan_operation_is_system_operation() -> None:
    """The loaded plan operation is a ProjectOperation instance."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    assert isinstance(op, ProjectOperation)


# ---------- task list structure ----------


def test_plan_operation_task_list_not_empty() -> None:
    """The plan operation has at least one task."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    assert len(op.tasks) > 0


def test_plan_operation_has_ensure_worktree() -> None:
    """The first task is BuiltIn('ensure_worktree')."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    first = op.tasks[0]
    assert isinstance(first, BuiltIn)
    assert first.name == "ensure_worktree"


def test_plan_operation_has_decompose_agent() -> None:
    """The operation includes an AgentTask named 'decompose'."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    agent_tasks = [t for t in op.tasks if isinstance(t, AgentTask)]
    assert any(t.name == "decompose" for t in agent_tasks), (
        f"No AgentTask named 'decompose'; agent tasks: {[t.name for t in agent_tasks]}"
    )


def test_plan_operation_decompose_agent_uses_opus() -> None:
    """The decompose AgentTask is pinned to opus model."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    agent_tasks = [
        t for t in op.tasks if isinstance(t, AgentTask) and t.name == "decompose"
    ]
    assert len(agent_tasks) == 1
    agent = agent_tasks[0]
    assert agent.model == "opus"
    assert agent.model_from_capability is False


def test_plan_operation_has_validate_shell_task() -> None:
    """The operation includes a ShellTask named 'validate' with retry_agent policy."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    shell_tasks = [t for t in op.tasks if isinstance(t, ShellTask)]
    validate_tasks = [t for t in shell_tasks if t.name == "validate"]
    assert len(validate_tasks) == 1
    assert validate_tasks[0].on_failure == "retry_agent"


def test_plan_operation_has_commit_push_pr() -> None:
    """The operation ends with commit, push_branch, and create_pr builtins."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
    op = operations["plan"]
    builtin_names = [t.name for t in op.tasks if isinstance(t, BuiltIn)]
    assert "commit" in builtin_names
    assert "push_branch" in builtin_names
    assert "create_pr" in builtin_names


# ---------- target requirement ----------


def test_plan_operation_requires_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the plan operation without --target is rejected by the CLI."""
    from darkfactory.cli import main

    _setup_project(tmp_path)
    ops_dir = _find_operations_dir()

    # Suppress builtin discovery — ops_dir IS the builtin dir, which would cause
    # duplicates if both layers scan the same path.
    empty = tmp_path / "_empty"
    empty.mkdir()
    monkeypatch.setenv("DARKFACTORY_BUILTINS_OPERATIONS_DIR", str(empty))

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--directory",
                str(tmp_path),
                "--workflows-dir",
                str(tmp_path / "workflows"),
                "--operations-dir",
                str(ops_dir),
                "project",
                "run",
                "plan",
            ]
        )
    # The CLI should exit non-zero when target is required but missing
    assert exc.value.code != 0


# ---------- CLI discoverability ----------


def test_plan_operation_discoverable_via_list(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prd project list shows the plan operation."""
    from darkfactory.cli import main

    _setup_project(tmp_path)
    ops_dir = _find_operations_dir()

    empty = tmp_path / "_empty"
    empty.mkdir()
    monkeypatch.setenv("DARKFACTORY_BUILTINS_OPERATIONS_DIR", str(empty))

    exit_code = main(
        [
            "--directory",
            str(tmp_path),
            "--workflows-dir",
            str(tmp_path / "workflows"),
            "--operations-dir",
            str(ops_dir),
            "project",
            "list",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "plan" in out
