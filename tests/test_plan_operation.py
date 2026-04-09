"""Tests for the plan system operation (PRD-223.6).

Covers:
- Operation loads and has accepts_target=True
- Operation is rejected without --target
- Task list is well-formed
- Operation is discoverable via prd system list
"""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.loader import load_operations
from darkfactory.system import SystemOperation
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask


# ---------- helpers ----------


def _find_operations_dir() -> Path:
    """Return the .darkfactory/operations/ directory relative to the repo root.

    Walks up from this test file until it finds the .darkfactory/ directory.
    """
    here = Path(__file__).resolve().parent
    for candidate in [here.parent, here.parent.parent]:
        ops = candidate / ".darkfactory" / "operations"
        if ops.exists():
            return ops
    raise FileNotFoundError(
        "Could not locate .darkfactory/operations/ directory from tests/"
    )


# ---------- operation loading ----------


def test_plan_operation_loads() -> None:
    """The plan operation.py loads without errors."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    assert "plan" in operations, (
        f"'plan' not found in operations; found: {list(operations)}"
    )


def test_plan_operation_accepts_target() -> None:
    """The plan operation has accepts_target=True."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    assert op.accepts_target is True


def test_plan_operation_creates_pr() -> None:
    """The plan operation has creates_pr=True."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    assert op.creates_pr is True


def test_plan_operation_is_system_operation() -> None:
    """The loaded plan operation is a SystemOperation instance."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    assert isinstance(op, SystemOperation)


# ---------- task list structure ----------


def test_plan_operation_task_list_not_empty() -> None:
    """The plan operation has at least one task."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    assert len(op.tasks) > 0


def test_plan_operation_has_ensure_worktree() -> None:
    """The first task is BuiltIn('ensure_worktree')."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    first = op.tasks[0]
    assert isinstance(first, BuiltIn)
    assert first.name == "ensure_worktree"


def test_plan_operation_has_decompose_agent() -> None:
    """The operation includes an AgentTask named 'decompose'."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    agent_tasks = [t for t in op.tasks if isinstance(t, AgentTask)]
    assert any(t.name == "decompose" for t in agent_tasks), (
        f"No AgentTask named 'decompose'; agent tasks: {[t.name for t in agent_tasks]}"
    )


def test_plan_operation_decompose_agent_uses_opus() -> None:
    """The decompose AgentTask is pinned to opus model."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
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
    operations = load_operations(ops_dir)
    op = operations["plan"]
    shell_tasks = [t for t in op.tasks if isinstance(t, ShellTask)]
    validate_tasks = [t for t in shell_tasks if t.name == "validate"]
    assert len(validate_tasks) == 1
    assert validate_tasks[0].on_failure == "retry_agent"


def test_plan_operation_has_commit_push_pr() -> None:
    """The operation ends with commit, push_branch, and create_pr builtins."""
    ops_dir = _find_operations_dir()
    operations = load_operations(ops_dir)
    op = operations["plan"]
    builtin_names = [t.name for t in op.tasks if isinstance(t, BuiltIn)]
    assert "commit" in builtin_names
    assert "push_branch" in builtin_names
    assert "create_pr" in builtin_names


# ---------- target requirement ----------


def test_plan_operation_requires_target(tmp_path: Path) -> None:
    """Running the plan operation without --target is rejected by the CLI."""
    from darkfactory.cli import main

    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = _find_operations_dir()

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(tmp_path / "workflows"),
                "--operations-dir",
                str(ops_dir),
                "system",
                "run",
                "plan",
            ]
        )
    # The CLI should exit non-zero when target is required but missing
    assert exc.value.code != 0


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


# ---------- CLI discoverability ----------


def test_plan_operation_discoverable_via_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd system list shows the plan operation."""
    from darkfactory.cli import main

    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = _find_operations_dir()

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(tmp_path / "workflows"),
            "--operations-dir",
            str(ops_dir),
            "system",
            "list",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "plan" in out
