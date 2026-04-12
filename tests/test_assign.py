"""Tests for workflow assignment logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from darkfactory.graph import assign_all, assign_workflow
from darkfactory.model import load_all
from darkfactory.workflow import BuiltIn, Workflow

from .conftest import write_prd


def _make_workflow(
    name: str,
    *,
    priority: int = 0,
    applies_to: Any = None,
) -> Workflow:
    """Construct a minimal Workflow for assignment tests."""
    if applies_to is None:
        return Workflow(
            name=name, priority=priority, tasks=[BuiltIn("ensure_worktree")]
        )
    return Workflow(
        name=name,
        priority=priority,
        tasks=[BuiltIn("ensure_worktree")],
        applies_to=applies_to,
    )


# ---------- explicit frontmatter field ----------


def test_explicit_workflow_field_wins(tmp_data_dir: Path) -> None:
    """If prd.workflow is set, it overrides predicate matching."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task", workflow="specific")
    prds = load_all(tmp_data_dir)

    default = _make_workflow("default", priority=0)
    specific = _make_workflow("specific", priority=10)
    workflows = {"default": default, "specific": specific}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is specific


def test_explicit_field_ignored_if_workflow_not_loaded(tmp_data_dir: Path) -> None:
    """If prd.workflow names a workflow that isn't registered, fall through to predicates."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task", workflow="nonexistent")
    prds = load_all(tmp_data_dir)

    default = _make_workflow(
        "default",
        applies_to=lambda prd, prds: True,
    )
    workflows = {"default": default}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is default


# ---------- predicate matching ----------


def test_highest_priority_predicate_wins(tmp_data_dir: Path) -> None:
    """Among matching predicates, the highest-priority workflow is chosen."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    low = _make_workflow(
        "low",
        priority=1,
        applies_to=lambda prd, prds: True,
    )
    high = _make_workflow(
        "high",
        priority=10,
        applies_to=lambda prd, prds: True,
    )
    workflows = {"low": low, "high": high}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is high


def test_alphabetical_tiebreak_on_equal_priority(tmp_data_dir: Path) -> None:
    """Equal priority -> alphabetical by name for determinism."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    bravo = _make_workflow(
        "bravo",
        priority=5,
        applies_to=lambda prd, prds: True,
    )
    alpha = _make_workflow(
        "alpha",
        priority=5,
        applies_to=lambda prd, prds: True,
    )
    workflows = {"bravo": bravo, "alpha": alpha}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is alpha


def test_only_matching_predicates_considered(tmp_data_dir: Path) -> None:
    """Workflows whose predicate returns False are ignored even at high priority."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task", kind="task")
    prds = load_all(tmp_data_dir)

    # High priority but doesn't match
    high_no_match = _make_workflow(
        "high",
        priority=100,
        applies_to=lambda prd, prds: prd.kind == "epic",
    )
    # Lower priority but matches
    low_match = _make_workflow(
        "low",
        priority=1,
        applies_to=lambda prd, prds: prd.kind == "task",
    )
    workflows = {"high": high_no_match, "low": low_match}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is low_match


# ---------- default fallback ----------


def test_default_fallback_when_no_predicate_matches(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    default = _make_workflow("default")  # default predicate returns False
    other = _make_workflow(
        "other",
        applies_to=lambda prd, prds: False,
    )
    workflows = {"default": default, "other": other}

    result = assign_workflow(prds["PRD-070"], prds, workflows)
    assert result is default


def test_raises_key_error_when_no_match_and_no_default(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    other = _make_workflow(
        "other",
        applies_to=lambda prd, prds: False,
    )
    workflows = {"other": other}

    with pytest.raises(KeyError, match="no workflow matches"):
        assign_workflow(prds["PRD-070"], prds, workflows)


# ---------- 1-arg vs 2-arg predicate compatibility ----------


def test_accepts_two_arg_predicate(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    wf = _make_workflow(
        "wf",
        priority=10,
        applies_to=lambda prd, prds: True,
    )
    workflows = {"wf": wf}
    assert assign_workflow(prds["PRD-070"], prds, workflows) is wf


def test_accepts_one_arg_legacy_predicate(tmp_data_dir: Path) -> None:
    """A legacy ``lambda prd: ...`` still works via TypeError fallback."""
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)

    wf = _make_workflow(
        "wf",
        priority=10,
        applies_to=lambda prd: True,
    )
    workflows = {"wf": wf}
    assert assign_workflow(prds["PRD-070"], prds, workflows) is wf


# ---------- bulk assignment ----------


def test_assign_all_returns_dict_keyed_by_id(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "one")
    write_prd(tmp_data_dir / "prds", "PRD-071", "two")
    write_prd(tmp_data_dir / "prds", "PRD-072", "three")
    prds = load_all(tmp_data_dir)

    default = _make_workflow("default")
    workflows = {"default": default}

    result = assign_all(prds, workflows)
    assert set(result.keys()) == {"PRD-070", "PRD-071", "PRD-072"}
    assert all(wf is default for wf in result.values())


def test_assign_all_respects_explicit_and_predicate_routing(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "one", workflow="special")
    write_prd(tmp_data_dir / "prds", "PRD-071", "two")
    prds = load_all(tmp_data_dir)

    default = _make_workflow("default")
    special = _make_workflow("special")
    workflows = {"default": default, "special": special}

    result = assign_all(prds, workflows)
    assert result["PRD-070"] is special
    assert result["PRD-071"] is default
