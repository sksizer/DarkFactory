"""Tests for cli/tree.py — tree formatting and display logic."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.tree import _format_tree_node, _print_tree, cmd_tree


def _make_prd(
    *,
    id: str,
    title: str = "A task",
    status: str = "ready",
    priority: str = "medium",
    kind: str = "task",
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.title = title
    prd.status = status
    prd.priority = priority
    prd.kind = kind
    return prd


def _make_plain_styler() -> MagicMock:
    """Return a styler that renders text as-is (no ANSI codes)."""
    styler = MagicMock()
    styler.kind_element.return_value = "kind"
    styler.icon.return_value = ""
    styler.render.side_effect = lambda _elem, text: text
    return styler


# ---------- _format_tree_node ----------


def test_format_tree_node_includes_id_and_title() -> None:
    prd = _make_prd(id="PRD-1", title="My Feature")
    styler = _make_plain_styler()
    result = _format_tree_node(prd, styler)
    assert "PRD-1" in result
    assert "My Feature" in result


def test_format_tree_node_includes_kind_and_status() -> None:
    prd = _make_prd(id="PRD-2", kind="epic", status="in-progress")
    styler = _make_plain_styler()
    result = _format_tree_node(prd, styler)
    assert "epic" in result
    assert "in-progress" in result


def test_format_tree_node_includes_priority() -> None:
    prd = _make_prd(id="PRD-3", priority="high")
    styler = _make_plain_styler()
    result = _format_tree_node(prd, styler)
    assert "high" in result


# ---------- _print_tree ----------


def test_print_tree_prints_connector_last(
    capsys: pytest.CaptureFixture[str],
) -> None:
    prd = _make_prd(id="PRD-10")
    prds = {"PRD-10": prd}
    styler = _make_plain_styler()
    with patch("darkfactory.cli.tree.containment.children", return_value=[]):
        _print_tree(prd, prds, styler, prefix="", is_last=True)
    out = capsys.readouterr().out
    assert "└──" in out


def test_print_tree_prints_connector_not_last(
    capsys: pytest.CaptureFixture[str],
) -> None:
    prd = _make_prd(id="PRD-11")
    prds = {"PRD-11": prd}
    styler = _make_plain_styler()
    with patch("darkfactory.cli.tree.containment.children", return_value=[]):
        _print_tree(prd, prds, styler, prefix="", is_last=False)
    out = capsys.readouterr().out
    assert "├──" in out


def test_print_tree_recurses_into_children(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent = _make_prd(id="PRD-20", title="Parent")
    child = _make_prd(id="PRD-20.1", title="Child")
    prds = {"PRD-20": parent, "PRD-20.1": child}
    styler = _make_plain_styler()

    def fake_children(prd_id: str, prds_map: dict[str, Any]) -> list[Any]:
        if prd_id == "PRD-20":
            return [child]
        return []

    with patch("darkfactory.cli.tree.containment.children", side_effect=fake_children):
        _print_tree(parent, prds, styler, prefix="", is_last=True)

    out = capsys.readouterr().out
    assert "Parent" in out
    assert "Child" in out


# ---------- cmd_tree ----------


def _make_args(prd_dir: Path, prd_id: str | None = None) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.prd_dir = prd_dir
    ns.prd_id = prd_id
    ns.styler = _make_plain_styler()
    return ns


def test_cmd_tree_all_roots(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root_prd = _make_prd(id="PRD-100", title="Root")
    prds = {"PRD-100": root_prd}
    args = _make_args(tmp_path)

    with (
        patch("darkfactory.cli.tree._load", return_value=prds),
        patch("darkfactory.cli.tree.containment.roots", return_value=[root_prd]),
        patch("darkfactory.cli.tree.containment.children", return_value=[]),
    ):
        rc = cmd_tree(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Root" in out


def test_cmd_tree_specific_prd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-200", title="Specific")
    prds = {"PRD-200": prd}
    args = _make_args(tmp_path, prd_id="PRD-200")

    with (
        patch("darkfactory.cli.tree._load", return_value=prds),
        patch("darkfactory.cli.tree.containment.children", return_value=[]),
    ):
        rc = cmd_tree(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Specific" in out


def test_cmd_tree_unknown_prd_id(tmp_path: Path) -> None:
    prds: dict[str, Any] = {}
    args = _make_args(tmp_path, prd_id="PRD-999")

    with (
        patch("darkfactory.cli.tree._load", return_value=prds),
        pytest.raises(SystemExit, match="unknown PRD id"),
    ):
        cmd_tree(args)
