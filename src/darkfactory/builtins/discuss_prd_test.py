"""Tests for discuss_prd system builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.builtins.discuss_prd import _print_phase_banner, discuss_prd
from darkfactory.system import SystemContext, SystemOperation


def _make_op(operation_dir: Path | None = None) -> SystemOperation:
    return SystemOperation(
        name="discuss",
        description="test",
        tasks=[],
        operation_dir=operation_dir,
    )


def _make_ctx(
    tmp_path: Path,
    operation_dir: Path | None = None,
    prd_context: str = "test context",
) -> SystemContext:
    ctx = SystemContext(
        repo_root=tmp_path,
        prds={},
        operation=_make_op(operation_dir),
        cwd=tmp_path,
        dry_run=False,
        target_prd="PRD-070",
    )
    ctx._shared_state["prd_context"] = prd_context
    return ctx


def _setup_prompt(tmp_path: Path) -> Path:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True)
    prompt_file = prompts_dir / "discuss.md"
    prompt_file.write_text("{PRD_CONTEXT}\n---\nPhase: {PHASE}\n", encoding="utf-8")
    return tmp_path


def test_discuss_prd_composes_prompt(tmp_path: Path) -> None:
    op_dir = _setup_prompt(tmp_path)
    ctx = _make_ctx(tmp_path, operation_dir=op_dir, prd_context="MY PRD CONTEXT")

    captured_prompts: list[str] = []

    def mock_spawn(prompt: str, cwd: Path) -> int:
        captured_prompts.append(prompt)
        return 0

    with patch(
        "darkfactory.builtins.discuss_prd._spawn_claude", side_effect=mock_spawn
    ):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            discuss_prd(ctx, phase="discuss", prompt_file="prompts/discuss.md")

    assert len(captured_prompts) == 1
    assert "MY PRD CONTEXT" in captured_prompts[0]
    assert "Phase: discuss" in captured_prompts[0]


def test_discuss_prd_prints_banner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    op_dir = _setup_prompt(tmp_path)
    ctx = _make_ctx(tmp_path, operation_dir=op_dir)

    with patch("darkfactory.builtins.discuss_prd._spawn_claude", return_value=0):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            discuss_prd(ctx, phase="discuss", prompt_file="prompts/discuss.md")

    captured = capsys.readouterr()
    assert "Phase: discuss" in captured.err
    assert "Ctrl-C" in captured.err


def test_discuss_prd_nonzero_exit_continues(tmp_path: Path) -> None:
    op_dir = _setup_prompt(tmp_path)
    ctx = _make_ctx(tmp_path, operation_dir=op_dir)

    with patch("darkfactory.builtins.discuss_prd._spawn_claude", return_value=1):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            discuss_prd(ctx, phase="discuss", prompt_file="prompts/discuss.md")


def test_discuss_prd_missing_prompt_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, operation_dir=tmp_path)

    with pytest.raises(FileNotFoundError, match="prompt file not found"):
        with patch("darkfactory.builtins.discuss_prd.time.sleep"):
            discuss_prd(ctx, phase="discuss", prompt_file="prompts/nonexistent.md")


def test_print_phase_banner(capsys: pytest.CaptureFixture[str]) -> None:
    _print_phase_banner("critique")
    captured = capsys.readouterr()
    assert "Phase: critique" in captured.err
    assert "Ctrl-C" in captured.err
