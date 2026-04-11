"""Integration tests for the discuss operation shape and chain order."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from conftest import write_prd
from darkfactory.commands.discuss import discuss_operation
from darkfactory.commands.discuss.operation import discuss_operation as op_from_module
from darkfactory.prd import load_all
from darkfactory.system import SystemContext, SystemOperation
from darkfactory.workflow import BuiltIn


def test_discuss_operation_exported() -> None:
    """AC-3: discuss_operation is exported from commands.discuss."""
    assert isinstance(discuss_operation, SystemOperation)
    assert discuss_operation is op_from_module


def test_discuss_operation_shape() -> None:
    """AC-3: Operation has correct metadata."""
    assert discuss_operation.name == "discuss"
    assert discuss_operation.requires_clean_main is False
    assert discuss_operation.creates_pr is False
    assert discuss_operation.accepts_target is True
    assert len(discuss_operation.tasks) == 4


def test_discuss_operation_task_order() -> None:
    """AC-6: Tasks are in the correct order."""
    tasks = discuss_operation.tasks
    assert isinstance(tasks[0], BuiltIn)
    assert tasks[0].name == "gather_prd_context"

    assert isinstance(tasks[1], BuiltIn)
    assert tasks[1].name == "discuss_prd"
    assert tasks[1].kwargs["phase"] == "discuss"

    assert isinstance(tasks[2], BuiltIn)
    assert tasks[2].name == "discuss_prd"
    assert tasks[2].kwargs["phase"] == "critique"

    assert isinstance(tasks[3], BuiltIn)
    assert tasks[3].name == "commit_prd_changes"


def test_prompt_files_exist() -> None:
    """AC-3: Prompt files exist in the package."""
    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
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
        / "src"
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
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "test-prd", title="Test PRD")
    prds = load_all(prd_dir)

    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    op = discuss_operation
    op.operation_dir = pkg_dir

    ctx = SystemContext(
        repo_root=tmp_path,
        prds=prds,
        operation=op,
        cwd=tmp_path,
        dry_run=False,
        target_prd="PRD-070",
    )

    call_order: list[str] = []

    def mock_spawn(prompt: str, cwd: Path) -> int:
        if "Collaborative" in prompt or "discuss" in prompt.lower()[:200]:
            call_order.append("discuss_claude")
        else:
            call_order.append("critique_claude")
        return 0

    with patch("darkfactory.builtins.discuss_prd.spawn_claude", side_effect=mock_spawn):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            with patch(
                "darkfactory.builtins.commit_prd_changes.diff_quiet",
                return_value=True,
            ):
                from darkfactory.system_runner import run_system_operation

                result = run_system_operation(op, ctx)

    assert result.success
    assert len(result.steps) == 4
    assert result.steps[0].name == "gather_prd_context"
    assert result.steps[1].name == "discuss_prd"
    assert result.steps[2].name == "discuss_prd"
    assert result.steps[3].name == "commit_prd_changes"


def test_nonzero_exit_does_not_abort_chain(tmp_path: Path) -> None:
    """AC-8: Non-zero exit from claude in discuss phase does not abort the chain."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "test-prd", title="Test PRD")
    prds = load_all(prd_dir)

    pkg_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "darkfactory"
        / "commands"
        / "discuss"
    )
    op = discuss_operation
    op.operation_dir = pkg_dir

    ctx = SystemContext(
        repo_root=tmp_path,
        prds=prds,
        operation=op,
        cwd=tmp_path,
        dry_run=False,
        target_prd="PRD-070",
    )

    with patch("darkfactory.builtins.discuss_prd.spawn_claude", return_value=130):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            with patch(
                "darkfactory.builtins.commit_prd_changes.diff_quiet",
                return_value=True,
            ):
                from darkfactory.system_runner import run_system_operation

                result = run_system_operation(op, ctx)

    assert result.success
    assert len(result.steps) == 4


def test_builtins_registered() -> None:
    """AC-4, AC-5, AC-12: All three builtins are registered in SYSTEM_BUILTINS."""
    from darkfactory.system_runner import SYSTEM_BUILTINS

    assert "gather_prd_context" in SYSTEM_BUILTINS
    assert "discuss_prd" in SYSTEM_BUILTINS
    assert "commit_prd_changes" in SYSTEM_BUILTINS
