"""Tests for the workflow loader."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from prd_harness.loader import load_workflows
from prd_harness.workflow import BuiltIn, Workflow


def _write_workflow(
    dir_path: Path,
    name: str,
    *,
    body: str | None = None,
) -> Path:
    """Create a ``workflows/<name>/workflow.py`` fixture file.

    ``body`` overrides the module body; otherwise a minimal valid workflow
    with one BuiltIn task is generated.
    """
    workflow_dir = dir_path / name
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = workflow_dir / "workflow.py"

    if body is None:
        body = f'''"""Fixture workflow."""
from prd_harness.workflow import BuiltIn, Workflow

workflow = Workflow(
    name={name!r},
    description="Fixture for tests",
    priority=5,
    tasks=[BuiltIn("ensure_worktree")],
)
'''
    workflow_file.write_text(body)
    return workflow_file


# ---------- empty / missing ----------


def test_load_workflows_missing_directory(tmp_path: Path) -> None:
    """A nonexistent directory returns an empty dict (not an error)."""
    result = load_workflows(tmp_path / "does-not-exist")
    assert result == {}


def test_load_workflows_empty_directory(tmp_path: Path) -> None:
    """An empty directory returns an empty dict."""
    result = load_workflows(tmp_path)
    assert result == {}


def test_load_workflows_skips_file_only_entries(tmp_path: Path) -> None:
    """Files at the top level are ignored; only subdirectories are scanned."""
    (tmp_path / "stray.py").write_text("# not a workflow")
    (tmp_path / "README.md").write_text("# top-level")
    result = load_workflows(tmp_path)
    assert result == {}


# ---------- successful load ----------


def test_load_single_workflow(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "default")
    result = load_workflows(tmp_path)
    assert "default" in result
    wf = result["default"]
    assert isinstance(wf, Workflow)
    assert wf.priority == 5
    assert wf.description == "Fixture for tests"
    assert len(wf.tasks) == 1
    assert isinstance(wf.tasks[0], BuiltIn)
    assert wf.tasks[0].name == "ensure_worktree"


def test_workflow_dir_is_set(tmp_path: Path) -> None:
    """The loader sets workflow.workflow_dir to the subdirectory path."""
    _write_workflow(tmp_path, "default")
    result = load_workflows(tmp_path)
    assert result["default"].workflow_dir == tmp_path / "default"


def test_load_multiple_workflows(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "alpha")
    _write_workflow(tmp_path, "bravo")
    _write_workflow(tmp_path, "charlie")
    result = load_workflows(tmp_path)
    assert set(result.keys()) == {"alpha", "bravo", "charlie"}


# ---------- directory filtering ----------


def test_load_skips_hidden_and_underscore_dirs(tmp_path: Path) -> None:
    """Subdirectories starting with . or _ are treated as private and skipped."""
    _write_workflow(tmp_path, "visible")
    _write_workflow(tmp_path, ".hidden")
    _write_workflow(tmp_path, "_private")
    result = load_workflows(tmp_path)
    assert set(result.keys()) == {"visible"}


def test_load_skips_dirs_without_workflow_py(tmp_path: Path) -> None:
    """Subdirectories without workflow.py are ignored silently."""
    _write_workflow(tmp_path, "has-workflow")
    (tmp_path / "no-workflow").mkdir()
    (tmp_path / "no-workflow" / "other.py").write_text("# not workflow.py")
    result = load_workflows(tmp_path)
    assert set(result.keys()) == {"has-workflow"}


# ---------- error handling ----------


def test_load_skips_workflows_with_syntax_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A broken workflow.py is logged and skipped; other workflows still load."""
    _write_workflow(tmp_path, "good")
    _write_workflow(
        tmp_path,
        "broken",
        body="this is not valid python syntax !@#$%\n",
    )
    with caplog.at_level(logging.WARNING, logger="prd_harness.loader"):
        result = load_workflows(tmp_path)
    assert "good" in result
    assert "broken" not in result
    assert any("failed to load workflow" in rec.message for rec in caplog.records)


def test_load_skips_workflows_missing_attribute(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A workflow.py that doesn't export `workflow` is logged and skipped."""
    _write_workflow(
        tmp_path,
        "bad",
        body="x = 42\n",  # no `workflow` attribute
    )
    with caplog.at_level(logging.WARNING, logger="prd_harness.loader"):
        result = load_workflows(tmp_path)
    assert result == {}
    assert any("failed to load workflow" in rec.message for rec in caplog.records)


def test_load_skips_workflows_with_wrong_type(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A module exporting `workflow` as the wrong type is logged and skipped."""
    _write_workflow(
        tmp_path,
        "wrong-type",
        body="workflow = 'not a Workflow instance'\n",
    )
    with caplog.at_level(logging.WARNING, logger="prd_harness.loader"):
        result = load_workflows(tmp_path)
    assert result == {}


def test_load_rejects_duplicate_names(tmp_path: Path) -> None:
    """Two modules both exporting `workflow = Workflow(name='foo')` raise ValueError."""
    _write_workflow(tmp_path, "first")
    _write_workflow(
        tmp_path,
        "second",
        body='''from prd_harness.workflow import Workflow
workflow = Workflow(name="first")  # deliberate collision
''',
    )
    with pytest.raises(ValueError, match="duplicate workflow name"):
        load_workflows(tmp_path)
