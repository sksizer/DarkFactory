"""Tests for Workflow (project operations), RunContext+ProjectRun, and load_operations."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from darkfactory.loader import load_operations
from darkfactory.engine import CodeEnv, PhaseState, ProjectRun
from darkfactory.workflow import BuiltIn, RunContext, Workflow


# ---------- helpers ----------


def _write_operation(
    dir_path: Path,
    name: str,
    *,
    body: str | None = None,
) -> Path:
    """Create an ``operations/<name>/workflow.py`` fixture file."""
    op_dir = dir_path / name
    op_dir.mkdir(parents=True, exist_ok=True)
    op_file = op_dir / "workflow.py"

    if body is None:
        body = f'''"""Fixture operation."""
from darkfactory.workflow import BuiltIn, Workflow

workflow = Workflow(
    name={name!r},
    description="Fixture for tests",
    tasks=[BuiltIn("some_builtin")],
)
'''
    op_file.write_text(body)
    return op_file


def _make_ctx(
    tmp_path: Path,
    *,
    op_name: str = "test-op",
    targets: list[str] | None = None,
    target_prd: str | None = None,
) -> RunContext:
    op = Workflow(
        name=op_name,
        description="test",
        tasks=[],
    )
    ctx = RunContext(dry_run=True)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(
        ProjectRun(
            workflow=op,
            prds={},
            targets=tuple(targets or []),
            target_prd=target_prd,
        )
    )
    return ctx


# ---------- Workflow (project operation) ----------


def test_project_operation_defaults(tmp_path: Path) -> None:
    op = Workflow(name="audit", description="desc", tasks=[])
    assert op.workflow_dir is None


def test_project_operation_with_tasks(tmp_path: Path) -> None:
    task = BuiltIn("my_builtin")
    op = Workflow(
        name="bulk",
        description="bulk op",
        tasks=[task],
    )
    assert op.tasks == [task]


# ---------- RunContext + ProjectRun ----------


def test_project_context_defaults(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert ctx.dry_run is True
    proj = ctx.state.get(ProjectRun)
    assert proj.targets == ()
    assert ctx.report == []
    assert proj.target_prd is None
    assert isinstance(ctx.state, PhaseState)


def test_project_context_logger_default(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert ctx.logger.name == "darkfactory"


# ---------- RunContext.format_string ----------


def test_format_string_operation_name(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, op_name="my-op")
    assert ctx.format_string("{workflow_name}") == "my-op"


def test_format_string_target_count(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, targets=["PRD-001", "PRD-002", "PRD-003"])
    assert ctx.format_string("{target_count}") == "3"


def test_format_string_target_prd_set(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, target_prd="PRD-042")
    assert ctx.format_string("{target_prd}") == "PRD-042"


def test_format_string_target_prd_not_set(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert ctx.format_string("{target_prd}") == ""


def test_format_string_combined(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, op_name="audit", targets=["a", "b"], target_prd="PRD-7")
    result = ctx.format_string(
        "op={workflow_name} count={target_count} prd={target_prd}"
    )
    assert result == "op=audit count=2 prd=PRD-7"


def test_format_string_unknown_key_passes_through(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    # RunContext.format_string leaves unknown placeholders unchanged
    result = ctx.format_string("{unknown_placeholder}")
    assert result == "{unknown_placeholder}"


# ---------- load_operations — empty / missing ----------


def test_load_operations_missing_directory(tmp_path: Path) -> None:
    result = load_operations(
        tmp_path / "does-not-exist", include_builtins=False, include_user=False
    )
    assert result == {}


def test_load_operations_empty_directory(tmp_path: Path) -> None:
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert result == {}


def test_load_operations_skips_files_at_top_level(tmp_path: Path) -> None:
    (tmp_path / "stray.py").write_text("# not an operation")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert result == {}


# ---------- load_operations — successful discovery ----------


def test_load_single_operation(tmp_path: Path) -> None:
    _write_operation(tmp_path, "audit")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert "audit" in result
    op = result["audit"]
    assert isinstance(op, Workflow)
    assert op.description == "Fixture for tests"
    assert len(op.tasks) == 1
    assert isinstance(op.tasks[0], BuiltIn)


def test_operation_dir_is_set(tmp_path: Path) -> None:
    _write_operation(tmp_path, "audit")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert result["audit"].workflow_dir == tmp_path / "audit"


def test_load_multiple_operations(tmp_path: Path) -> None:
    _write_operation(tmp_path, "alpha")
    _write_operation(tmp_path, "bravo")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert set(result.keys()) == {"alpha", "bravo"}


# ---------- load_operations — directory filtering ----------


def test_load_skips_hidden_and_underscore_dirs(tmp_path: Path) -> None:
    _write_operation(tmp_path, "visible")
    _write_operation(tmp_path, ".hidden")
    _write_operation(tmp_path, "_private")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert set(result.keys()) == {"visible"}


def test_load_skips_dirs_without_operation_py(tmp_path: Path) -> None:
    _write_operation(tmp_path, "has-op")
    (tmp_path / "no-op").mkdir()
    (tmp_path / "no-op" / "other.py").write_text("# not workflow.py")
    result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert set(result.keys()) == {"has-op"}


# ---------- load_operations — error handling ----------


def test_load_skips_operations_with_syntax_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_operation(tmp_path, "good")
    _write_operation(tmp_path, "broken", body="this is not valid python !@#$\n")
    with caplog.at_level(logging.WARNING, logger="darkfactory.loader"):
        result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert "good" in result
    assert "broken" not in result
    assert any("failed to load" in rec.message for rec in caplog.records)


def test_load_skips_operations_missing_attribute(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_operation(tmp_path, "bad", body="x = 42\n")
    with caplog.at_level(logging.WARNING, logger="darkfactory.loader"):
        result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert result == {}
    assert any("failed to load" in rec.message for rec in caplog.records)


def test_load_skips_operations_with_wrong_type(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_operation(tmp_path, "wrong", body="workflow = 'not a Workflow'\n")
    with caplog.at_level(logging.WARNING, logger="darkfactory.loader"):
        result = load_operations(tmp_path, include_builtins=False, include_user=False)
    assert result == {}


def test_load_rejects_duplicate_names(tmp_path: Path) -> None:
    _write_operation(tmp_path, "first")
    _write_operation(
        tmp_path,
        "second",
        body="""from darkfactory.workflow import Workflow
workflow = Workflow(name="first", description="dup", tasks=[])
""",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_operations(tmp_path, include_builtins=False, include_user=False)
