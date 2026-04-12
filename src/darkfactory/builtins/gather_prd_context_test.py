"""Tests for gather_prd_context system builtin."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import write_prd
from darkfactory.builtins.gather_prd_context import gather_prd_context
from darkfactory.model import PRD, load_all
from darkfactory.phase_state import PrdContext
from darkfactory.system import SystemContext, SystemOperation


def _make_op() -> SystemOperation:
    return SystemOperation(name="test-op", description="test", tasks=[])


def _make_ctx(
    tmp_path: Path,
    prds: dict[str, PRD] | None = None,
    target_prd: str | None = None,
) -> SystemContext:
    ctx = SystemContext(
        repo_root=tmp_path,
        prds=prds or {},
        operation=_make_op(),
        cwd=tmp_path,
        dry_run=False,
        target_prd=target_prd,
    )
    return ctx


def test_gather_context_basic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-070", "test-prd", title="Test PRD", status="draft")
    prds = load_all(data_dir)

    ctx = _make_ctx(tmp_path, prds=prds, target_prd="PRD-070")
    gather_prd_context(ctx)

    context = ctx.state.get(PrdContext).body
    assert "## Target PRD" in context
    assert "PRD-070" in context
    assert "Test PRD" in context
    assert "draft" in context


def test_gather_context_with_parent_and_deps(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "parent", title="Parent Epic", kind="epic")
    write_prd(prds_dir, "PRD-002", "dep-a", title="Dependency A")
    write_prd(prds_dir, "PRD-003", "dep-b", title="Dependency B")
    write_prd(
        prds_dir,
        "PRD-070",
        "target",
        title="Target PRD",
        parent="PRD-001",
        depends_on=["PRD-002", "PRD-003"],
    )
    prds = load_all(data_dir)

    ctx = _make_ctx(tmp_path, prds=prds, target_prd="PRD-070")
    gather_prd_context(ctx)

    context = ctx.state.get(PrdContext).body
    assert "## Parent" in context
    assert "PRD-001" in context
    assert "Parent Epic" in context
    assert "## Dependencies" in context
    assert "PRD-002" in context
    assert "Dependency A" in context
    assert "PRD-003" in context
    assert "Dependency B" in context


def test_gather_context_missing_target_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, target_prd="PRD-999")
    with pytest.raises(ValueError, match="not found"):
        gather_prd_context(ctx)


def test_gather_context_no_target_prd_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, target_prd=None)
    with pytest.raises(ValueError, match="requires ctx.target_prd"):
        gather_prd_context(ctx)


def test_gather_context_missing_dep_graceful(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(
        prds_dir,
        "PRD-070",
        "target",
        title="Target",
        depends_on=["PRD-999"],
    )
    prds = load_all(data_dir)

    ctx = _make_ctx(tmp_path, prds=prds, target_prd="PRD-070")
    gather_prd_context(ctx)

    context = ctx.state.get(PrdContext).body
    assert "PRD-999" in context
    assert "(not found)" in context
