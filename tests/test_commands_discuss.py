"""Integration tests for the discuss operation shape and chain order."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from darkfactory.utils.git._types import Ok

from conftest import write_prd
from darkfactory.commands.discuss import discuss_operation
from darkfactory.commands.discuss.operation import discuss_operation as op_from_module
from darkfactory.engine import CodeEnv, ProjectRun
from darkfactory.model import load_all
from darkfactory.workflow import BuiltIn, InteractiveTask, RunContext, Workflow


def test_discuss_operation_exported() -> None:
    """AC-3: discuss_operation is exported from commands.discuss."""
    assert isinstance(discuss_operation, Workflow)
    assert discuss_operation is op_from_module


def test_discuss_operation_shape() -> None:
    """AC-3: Operation has correct metadata."""
    assert discuss_operation.name == "discuss"
    assert len(discuss_operation.tasks) == 4


def test_discuss_operation_task_order() -> None:
    """AC-6: Tasks are in the correct order."""
    tasks = discuss_operation.tasks
    assert isinstance(tasks[0], BuiltIn)
    assert tasks[0].name == "gather_prd_context"

    assert isinstance(tasks[1], InteractiveTask)
    assert tasks[1].name == "discuss"
    assert tasks[1].prompt_file == "prompts/discuss.md"
    assert tasks[1].effort_level == "max"

    assert isinstance(tasks[2], InteractiveTask)
    assert tasks[2].name == "critique"
    assert tasks[2].prompt_file == "prompts/critique.md"
    assert tasks[2].effort_level == "max"

    assert isinstance(tasks[3], BuiltIn)
    assert tasks[3].name == "commit_prd_changes"


def test_prompt_files_exist() -> None:
    """AC-3: Prompt files exist in the package."""
    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "python"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    assert (pkg_dir / "prompts" / "discuss.md").exists()
    assert (pkg_dir / "prompts" / "critique.md").exists()


def test_prompt_files_have_placeholders() -> None:
    """AC-5: Prompt files contain expected placeholders."""
    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "python"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    for name in ("discuss.md", "critique.md"):
        content = (pkg_dir / "prompts" / name).read_text(encoding="utf-8")
        assert "{PRD_CONTEXT}" in content
        assert "{PHASE}" in content


def test_chain_executes_in_order(tmp_path: Path) -> None:
    """AC-6: Full chain executes tasks in order with mocked subprocess."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-070", "test-prd", title="Test PRD")
    prds = load_all(data_dir)

    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "python"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    op = discuss_operation
    op.workflow_dir = pkg_dir

    ctx = RunContext(dry_run=False)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(
        ProjectRun(
            workflow=op,
            prds=prds,
            targets=tuple(prds.keys()),
            target_prd="PRD-070",
        )
    )

    call_order: list[str] = []

    def mock_spawn(
        prompt: str,
        cwd: Path,
        *,
        effort_level: str | None = None,
    ) -> int:
        if "Collaborative" in prompt or "discuss" in prompt.lower()[:200]:
            call_order.append("discuss_claude")
        else:
            call_order.append("critique_claude")
        return 0

    with patch("darkfactory.runner.spawn_claude", side_effect=mock_spawn):
        with patch("darkfactory.runner.time.sleep"):
            with patch(
                "darkfactory.operations.commit_prd_changes.diff_quiet",
                return_value=Ok(None),
            ):
                from darkfactory.runner import run_project_operation

                result = run_project_operation(op, ctx)

    assert result.success
    assert len(result.steps) == 4
    assert result.steps[0].name == "gather_prd_context"
    assert result.steps[1].name == "discuss"
    assert result.steps[2].name == "critique"
    assert result.steps[3].name == "commit_prd_changes"


def test_nonzero_exit_does_not_abort_chain(tmp_path: Path) -> None:
    """AC-8: Non-zero exit from claude in discuss phase does not abort the chain."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-070", "test-prd", title="Test PRD")
    prds = load_all(data_dir)

    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "python"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    op = discuss_operation
    op.workflow_dir = pkg_dir

    ctx = RunContext(dry_run=False)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(
        ProjectRun(
            workflow=op,
            prds=prds,
            targets=tuple(prds.keys()),
            target_prd="PRD-070",
        )
    )

    with patch("darkfactory.runner.spawn_claude", return_value=130):
        with patch("darkfactory.runner.time.sleep"):
            with patch(
                "darkfactory.operations.commit_prd_changes.diff_quiet",
                return_value=Ok(None),
            ):
                from darkfactory.runner import run_project_operation

                result = run_project_operation(op, ctx)

    assert result.success
    assert len(result.steps) == 4


def test_builtins_registered() -> None:
    """AC-4, AC-5, AC-12: All three builtins are registered in SYSTEM_BUILTINS."""
    from darkfactory.operations.project_builtins import SYSTEM_BUILTINS

    assert "gather_prd_context" in SYSTEM_BUILTINS
    assert "discuss_prd" in SYSTEM_BUILTINS
    assert "commit_prd_changes" in SYSTEM_BUILTINS
