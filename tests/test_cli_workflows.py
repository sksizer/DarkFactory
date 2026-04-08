"""Integration tests for the list-workflows and assign CLI subcommands.

These tests exercise the full CLI stack (argparse -> loader -> assign ->
print) against fixture PRD and workflow directories. They're named
``test_cli_workflows.py`` rather than extending the existing
``test_cli.py`` to keep CI output scannable and because PRD-206's
scope is specifically the two new commands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from darkfactory.cli import main
from darkfactory.prd import load_all

from .conftest import write_prd


def _write_default_workflow(dir_path: Path) -> None:
    """Create a fixture `default` workflow at ``dir_path/default/workflow.py``."""
    default_dir = dir_path / "default"
    default_dir.mkdir(parents=True)
    (default_dir / "workflow.py").write_text(
        '''"""Fixture default workflow."""
from darkfactory.workflow import BuiltIn, Workflow

workflow = Workflow(
    name="default",
    description="Catchall fallback for tests.",
    applies_to=lambda prd, prds: True,
    priority=0,
    tasks=[BuiltIn("ensure_worktree"), BuiltIn("create_pr")],
)
'''
    )


def _write_ui_workflow(dir_path: Path) -> None:
    """Create a fixture `ui` workflow that matches PRDs tagged `ui`."""
    ui_dir = dir_path / "ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "workflow.py").write_text(
        '''"""Fixture UI workflow."""
from darkfactory.workflow import BuiltIn, Workflow


def _matches(prd, prds):
    return "ui" in prd.tags


workflow = Workflow(
    name="ui",
    description="UI-component specialization for tests.",
    applies_to=_matches,
    priority=10,
    tasks=[BuiltIn("ensure_worktree")],
)
'''
    )


# ---------- list-workflows ----------


def test_list_workflows_shows_loaded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """list-workflows dumps each loaded workflow with priority and description."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)

    # Need a PRD dir too so --prd-dir has something valid (not used by this cmd
    # but required by the global flag default).
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "placeholder")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "list-workflows",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "default" in captured.out
    assert "priority=0" in captured.out
    assert "Catchall fallback" in captured.out


def test_list_workflows_orders_by_priority_desc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Higher-priority workflows appear first in the output."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)
    _write_ui_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "placeholder")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "list-workflows",
        ]
    )
    out = capsys.readouterr().out
    ui_pos = out.find("ui")
    default_pos = out.find("default")
    assert ui_pos < default_pos, "higher priority (ui) should appear first"


def test_list_workflows_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json produces a valid JSON array."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "placeholder")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "--json",
            "list-workflows",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["name"] == "default"
    assert payload[0]["priority"] == 0
    assert payload[0]["task_count"] == 2


def test_list_workflows_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """list-workflows with an empty workflows dir prints a friendly message."""
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "placeholder")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "list-workflows",
        ]
    )
    assert "no workflows loaded" in capsys.readouterr().out


# ---------- assign ----------


def test_assign_predicate_routing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each PRD is routed by the assignment logic and the source is shown."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)
    _write_ui_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "backend-task")
    # The fixture write_prd doesn't currently support a tags kwarg, so
    # we verify the routing path via the default predicate only. The
    # explicit-workflow test below covers the non-default case.

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "assign",
        ]
    )
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "default" in out
    assert "predicate" in out


def test_assign_explicit_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PRDs with an explicit workflow field show 'explicit' in the Source column."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)
    _write_ui_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "explicit-task", workflow="ui")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "assign",
        ]
    )
    out = capsys.readouterr().out
    # The row should show PRD-001 -> ui as explicit
    assert "PRD-001" in out
    assert "ui" in out
    assert "explicit" in out


def test_assign_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--json produces a list of {id, workflow, explicit} records."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "first")
    write_prd(prd_dir, "PRD-002", "second", workflow="default")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "--json",
            "assign",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 2
    # Sorted by natural id
    assert payload[0]["id"] == "PRD-001"
    assert payload[0]["workflow"] == "default"
    assert payload[0]["explicit"] is False
    assert payload[1]["id"] == "PRD-002"
    assert payload[1]["explicit"] is True


def test_assign_write_persists_to_frontmatter(tmp_path: Path) -> None:
    """--write persists the resolved workflow into each PRD's frontmatter."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "first")
    write_prd(prd_dir, "PRD-002", "second")

    # Before: no workflow field set
    before = load_all(prd_dir)
    assert before["PRD-001"].workflow is None

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "assign",
            "--write",
        ]
    )
    assert exit_code == 0

    # After: workflow field should be 'default' for both PRDs
    after = load_all(prd_dir)
    assert after["PRD-001"].workflow == "default"
    assert after["PRD-002"].workflow == "default"


def test_assign_write_is_idempotent(tmp_path: Path) -> None:
    """--write doesn't overwrite existing explicit workflow assignments."""
    workflows_dir = tmp_path / "workflows"
    _write_default_workflow(workflows_dir)
    _write_ui_workflow(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    # PRD-001 has explicit "ui" workflow pinned
    write_prd(prd_dir, "PRD-001", "first", workflow="ui")
    write_prd(prd_dir, "PRD-002", "second")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "assign",
            "--write",
        ]
    )

    after = load_all(prd_dir)
    # Explicit assignment preserved
    assert after["PRD-001"].workflow == "ui"
    # Second got the default
    assert after["PRD-002"].workflow == "default"


def test_assign_missing_workflows_dir_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing workflows directory produces a friendly SystemExit."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "first")

    with pytest.raises(SystemExit, match="workflows directory not found"):
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(tmp_path / "does-not-exist"),
                "assign",
            ]
        )
