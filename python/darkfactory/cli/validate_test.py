"""Tests for cli/validate.py — cmd_validate validation logic."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.validate import cmd_validate


def _make_prd(
    *,
    id: str,
    path_name: str | None = None,
    title: str = "A task",
    status: str = "ready",
    kind: str = "task",
    priority: str = "medium",
    effort: str = "s",
    capability: str = "simple",
    parent: str | None = None,
    depends_on: list[str] | None = None,
    blocks: list[str] | None = None,
    impacts: list[str] | None = None,
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.path = MagicMock()
    prd.path.name = path_name if path_name is not None else f"{id}-title.md"
    prd.title = title
    prd.status = status
    prd.kind = kind
    prd.priority = priority
    prd.effort = effort
    prd.capability = capability
    prd.parent = parent
    prd.depends_on = depends_on or []
    prd.blocks = blocks or []
    prd.impacts = impacts or []
    return prd


def _make_args(data_dir: Path, *, verbose: bool = False) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.data_dir = data_dir
    ns.verbose = verbose
    return ns


def _git_patches() -> list[AbstractContextManager[Any]]:
    """Stack of patches that stub out git-dependent helpers."""
    return [
        patch("darkfactory.cli.validate._find_repo_root", return_value=Path("/fake")),
        patch("darkfactory.cli.validate.impacts.tracked_files", return_value=[]),
        patch(
            "darkfactory.cli.validate.checks.SubprocessGitState",
            side_effect=Exception("no git"),
        ),
    ]


def _with_git_patches(fn: Callable[[], Any]) -> Any:
    """Helper to run *fn* with all git patches active."""
    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _git_patches():
            stack.enter_context(p)
        return fn()


# ---------- filename / id consistency ----------


def test_filename_id_mismatch_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", path_name="PRD-002-something.md")
    prds = {"PRD-001": prd}

    def run() -> int:
        with patch("darkfactory.cli.validate._load", return_value=prds):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "does not match filename" in captured.err


def test_filename_id_match_is_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", path_name="PRD-001-my-task.md")
    prds = {"PRD-001": prd}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 0
    captured = capsys.readouterr()
    assert "OK: 1 PRDs valid" in captured.out


# ---------- wikilink / reference resolution ----------


def test_unknown_depends_on_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", depends_on=["PRD-999"])
    prds = {"PRD-001": prd}

    def run() -> int:
        with patch("darkfactory.cli.validate._load", return_value=prds):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "depends_on references unknown PRD-999" in captured.err


def test_unknown_blocks_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", blocks=["PRD-999"])
    prds = {"PRD-001": prd}

    def run() -> int:
        with patch("darkfactory.cli.validate._load", return_value=prds):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "blocks references unknown PRD-999" in captured.err


def test_unknown_parent_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001", parent="PRD-999")
    prds = {"PRD-001": prd}

    def run() -> int:
        with patch("darkfactory.cli.validate._load", return_value=prds):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "parent references unknown PRD-999" in captured.err


def test_known_references_are_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parent = _make_prd(id="PRD-001", kind="epic")
    child = _make_prd(id="PRD-001.1", parent="PRD-001", depends_on=["PRD-001"])
    prds = {"PRD-001": parent, "PRD-001.1": child}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 0


# ---------- cycle detection ----------


def test_dependency_cycle_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_a = _make_prd(id="PRD-001", depends_on=["PRD-002"])
    prd_b = _make_prd(id="PRD-002", depends_on=["PRD-001"])
    prds = {"PRD-001": prd_a, "PRD-002": prd_b}
    fake_cycle = ["PRD-001", "PRD-002"]

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch(
                "darkfactory.cli.validate.graph.detect_cycles",
                return_value=[fake_cycle],
            ),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "dependency cycle" in captured.err


def test_containment_cycle_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # PRD-001.parent = PRD-002, PRD-002.parent = PRD-001 → cycle
    prd_a = _make_prd(id="PRD-001", parent="PRD-002")
    prd_b = _make_prd(id="PRD-002", parent="PRD-001")
    prds = {"PRD-001": prd_a, "PRD-002": prd_b}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "containment cycle" in captured.err


# ---------- container impacts check ----------


def test_container_with_declared_impacts_produces_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parent = _make_prd(id="PRD-001", impacts=["src/foo.py"])
    child_mock = MagicMock()
    prds = {"PRD-001": parent}

    def fake_children(prd_id: str, prds_dict: dict[str, Any]) -> list[Any]:
        return [child_mock] if prd_id == "PRD-001" else []

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch(
                "darkfactory.cli.validate.containment.children",
                side_effect=fake_children,
            ),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 1
    captured = capsys.readouterr()
    assert "container PRD" in captured.err


# ---------- impact overlap warnings ----------


def test_impact_overlap_warns_but_returns_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two ready PRDs with overlapping impacts and no dep produce a warning, not an error."""
    prd_a = _make_prd(id="PRD-001", impacts=["src/shared.py"])
    prd_b = _make_prd(id="PRD-002", impacts=["src/shared.py"])
    prds = {"PRD-001": prd_a, "PRD-002": prd_b}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
            patch(
                "darkfactory.cli.validate._find_repo_root",
                return_value=Path("/fake"),
            ),
            patch(
                "darkfactory.cli.validate.impacts.tracked_files",
                return_value=["src/shared.py"],
            ),
            patch(
                "darkfactory.cli.validate.impacts.impacts_overlap",
                return_value={"src/shared.py"},
            ),
            patch(
                "darkfactory.cli.validate.checks.SubprocessGitState",
                side_effect=Exception("no git"),
            ),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = run()
    assert result == 0
    captured = capsys.readouterr()
    assert "overlapping impacts" in captured.err
    assert "1 files" in captured.err


# ---------- verbose undeclared impacts ----------


def test_undeclared_impacts_warn_in_verbose_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ready leaf PRDs with no impacts produce a warning when --verbose is set."""
    prd = _make_prd(id="PRD-001", impacts=[])
    prds = {"PRD-001": prd}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path, verbose=True))

    result = _with_git_patches(run)
    assert result == 0
    captured = capsys.readouterr()
    assert "no declared impacts" in captured.err


def test_undeclared_impacts_silent_without_verbose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --verbose, undeclared impacts are not warned about."""
    prd = _make_prd(id="PRD-001", impacts=[])
    prds = {"PRD-001": prd}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path, verbose=False))

    result = _with_git_patches(run)
    assert result == 0
    captured = capsys.readouterr()
    assert "no declared impacts" not in captured.err


# ---------- review-branch warnings ----------


def test_review_branch_issue_produces_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """validate_review_branches issues appear as warnings, exit code stays 0."""
    prd = _make_prd(id="PRD-001")
    prds = {"PRD-001": prd}

    fake_issue = MagicMock()
    fake_issue.message = "PRD-001: review branch prd/PRD-001 not found on origin"

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
            patch(
                "darkfactory.cli.validate._find_repo_root",
                return_value=Path("/fake"),
            ),
            patch(
                "darkfactory.cli.validate.impacts.tracked_files",
                return_value=[],
            ),
            patch("darkfactory.cli.validate.checks.SubprocessGitState"),
            patch(
                "darkfactory.cli.validate.checks.validate_review_branches",
                return_value=[fake_issue],
            ),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = run()
    assert result == 0
    captured = capsys.readouterr()
    assert "review branch" in captured.err
    assert "not found on origin" in captured.err


# ---------- cmd_validate overall OK path ----------


def test_validate_ok_returns_0_and_prints_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd = _make_prd(id="PRD-001")
    prds = {"PRD-001": prd}

    def run() -> int:
        with (
            patch("darkfactory.cli.validate._load", return_value=prds),
            patch("darkfactory.cli.validate.graph.build_graph", return_value={}),
            patch("darkfactory.cli.validate.graph.detect_cycles", return_value=[]),
            patch("darkfactory.cli.validate.containment.children", return_value=[]),
        ):
            return cmd_validate(_make_args(tmp_path))

    result = _with_git_patches(run)
    assert result == 0
    captured = capsys.readouterr()
    assert "OK: 1 PRDs valid" in captured.out
