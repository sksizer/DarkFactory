"""Tests for the containment tree."""

from __future__ import annotations

from pathlib import Path

from darkfactory import containment
from darkfactory.prd import load_all

from .conftest import write_prd


def test_children(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat-a", parent="PRD-001")
    write_prd(tmp_prd_dir, "PRD-011", "feat-b", parent="PRD-001")
    write_prd(tmp_prd_dir, "PRD-020", "other-feat", parent=None)
    prds = load_all(tmp_prd_dir)
    kids = containment.children("PRD-001", prds)
    assert [k.id for k in kids] == ["PRD-010", "PRD-011"]


def test_descendants_recurses(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    write_prd(tmp_prd_dir, "PRD-070", "task-a", kind="task", parent="PRD-010")
    write_prd(tmp_prd_dir, "PRD-071", "task-b", kind="task", parent="PRD-010")
    prds = load_all(tmp_prd_dir)
    desc = containment.descendants("PRD-001", prds)
    assert {p.id for p in desc} == {"PRD-010", "PRD-070", "PRD-071"}


def test_ancestors_walks_up(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    write_prd(tmp_prd_dir, "PRD-070", "task", kind="task", parent="PRD-010")
    prds = load_all(tmp_prd_dir)
    chain = containment.ancestors("PRD-070", prds)
    assert [a.id for a in chain] == ["PRD-010", "PRD-001"]


def test_roots(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic1", kind="epic")
    write_prd(tmp_prd_dir, "PRD-002", "epic2", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    rs = containment.roots(prds)
    assert {r.id for r in rs} == {"PRD-001", "PRD-002"}


def test_is_leaf(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    assert containment.is_leaf(prds["PRD-010"], prds)
    assert not containment.is_leaf(prds["PRD-001"], prds)


def test_is_fully_decomposed_true(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-070", "task", kind="task", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    assert containment.is_fully_decomposed(prds["PRD-001"], prds)


def test_is_fully_decomposed_false_no_tasks(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    assert not containment.is_fully_decomposed(prds["PRD-001"], prds)


def test_is_runnable_task_kind(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "task", kind="task")
    prds = load_all(tmp_prd_dir)
    assert containment.is_runnable(prds["PRD-001"], prds)


def test_is_runnable_leaf_feature(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "feat", kind="feature")
    prds = load_all(tmp_prd_dir)
    assert containment.is_runnable(prds["PRD-001"], prds)


def test_is_runnable_epic_with_children_is_not(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-010", "feat", kind="feature", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    assert not containment.is_runnable(prds["PRD-001"], prds)
