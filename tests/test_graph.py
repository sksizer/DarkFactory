"""Tests for graph operations: build, cycles, topo sort, actionability."""

from __future__ import annotations

from pathlib import Path

from darkfactory import graph
from darkfactory.model import load_all

from .conftest import write_prd


def test_build_graph_empty(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "lone")
    g = graph.build_graph(load_all(tmp_data_dir))
    assert g == {"PRD-001": set()}


def test_build_graph_with_edges(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "first")
    write_prd(tmp_data_dir / "prds", "PRD-002", "second", depends_on=["PRD-001"])
    write_prd(
        tmp_data_dir / "prds", "PRD-003", "third", depends_on=["PRD-001", "PRD-002"]
    )
    g = graph.build_graph(load_all(tmp_data_dir))
    # PRD-001 has downstream edges to both 002 and 003
    assert g["PRD-001"] == {"PRD-002", "PRD-003"}
    assert g["PRD-002"] == {"PRD-003"}
    assert g["PRD-003"] == set()


def test_detect_cycles_acyclic(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a")
    write_prd(tmp_data_dir / "prds", "PRD-002", "b", depends_on=["PRD-001"])
    write_prd(tmp_data_dir / "prds", "PRD-003", "c", depends_on=["PRD-002"])
    cycles = graph.detect_cycles(graph.build_graph(load_all(tmp_data_dir)))
    assert cycles == []


def test_detect_cycles_self_loop(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", depends_on=["PRD-001"])
    cycles = graph.detect_cycles(graph.build_graph(load_all(tmp_data_dir)))
    assert len(cycles) == 1
    assert cycles[0] == ["PRD-001"]


def test_detect_cycles_two_node_cycle(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", depends_on=["PRD-002"])
    write_prd(tmp_data_dir / "prds", "PRD-002", "b", depends_on=["PRD-001"])
    cycles = graph.detect_cycles(graph.build_graph(load_all(tmp_data_dir)))
    assert len(cycles) == 1
    assert set(cycles[0]) == {"PRD-001", "PRD-002"}


def test_topological_sort_linear(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a")
    write_prd(tmp_data_dir / "prds", "PRD-002", "b", depends_on=["PRD-001"])
    write_prd(tmp_data_dir / "prds", "PRD-003", "c", depends_on=["PRD-002"])
    order = graph.topological_sort(graph.build_graph(load_all(tmp_data_dir)))
    assert order == ["PRD-001", "PRD-002", "PRD-003"]


def test_topological_sort_diamond(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a")
    write_prd(tmp_data_dir / "prds", "PRD-002", "b", depends_on=["PRD-001"])
    write_prd(tmp_data_dir / "prds", "PRD-003", "c", depends_on=["PRD-001"])
    write_prd(tmp_data_dir / "prds", "PRD-004", "d", depends_on=["PRD-002", "PRD-003"])
    order = graph.topological_sort(graph.build_graph(load_all(tmp_data_dir)))
    # Root first, leaf last; siblings in id order
    assert order[0] == "PRD-001"
    assert order[-1] == "PRD-004"
    assert order.index("PRD-002") < order.index("PRD-003")  # tie-break by id


def test_transitive_blocks(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a")
    write_prd(tmp_data_dir / "prds", "PRD-002", "b", depends_on=["PRD-001"])
    write_prd(tmp_data_dir / "prds", "PRD-003", "c", depends_on=["PRD-002"])
    write_prd(tmp_data_dir / "prds", "PRD-004", "d", depends_on=["PRD-001"])
    g = graph.build_graph(load_all(tmp_data_dir))
    blocks = graph.transitive_blocks(g, "PRD-001")
    assert set(blocks) == {"PRD-002", "PRD-003", "PRD-004"}


def test_is_actionable_ready_with_done_dep(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", status="done")
    write_prd(
        tmp_data_dir / "prds", "PRD-002", "b", status="ready", depends_on=["PRD-001"]
    )
    prds = load_all(tmp_data_dir)
    assert graph.is_actionable(prds["PRD-002"], prds)


def test_is_actionable_blocked_by_open_dep(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", status="ready")
    write_prd(
        tmp_data_dir / "prds", "PRD-002", "b", status="ready", depends_on=["PRD-001"]
    )
    prds = load_all(tmp_data_dir)
    assert not graph.is_actionable(prds["PRD-002"], prds)


def test_is_actionable_ignores_draft(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", status="draft")
    prds = load_all(tmp_data_dir)
    assert not graph.is_actionable(prds["PRD-001"], prds)


def test_missing_deps(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-001", "a", depends_on=["PRD-999"])
    prds = load_all(tmp_data_dir)
    assert graph.missing_deps(prds["PRD-001"], prds) == ["PRD-999"]
