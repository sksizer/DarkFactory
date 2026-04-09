"""Tests for the audit-impacts system operation and its audit_impacts_check builtin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from darkfactory.builtins.system_builtins import (
    SYSTEM_BUILTINS,
    audit_impacts_check,
)
from darkfactory.loader import load_operations
from darkfactory.prd import PRD, parse_prd
from darkfactory.system import SystemContext, SystemOperation
from darkfactory.system_runner import run_system_operation

from tests.conftest import write_prd


# ---------- helpers ----------


def _make_op() -> SystemOperation:
    return SystemOperation(name="test-op", description="test", tasks=[])


def _make_ctx(
    tmp_path: Path,
    prds: dict[str, PRD] | None = None,
    *,
    dry_run: bool = False,
) -> SystemContext:
    return SystemContext(
        repo_root=tmp_path,
        prds=prds or {},
        operation=_make_op(),
        cwd=tmp_path,
        dry_run=dry_run,
    )


def _write_and_parse(tmp_path: Path, prd_id: str, slug: str, **kwargs: Any) -> PRD:
    write_prd(tmp_path, prd_id, slug, **kwargs)
    return parse_prd(tmp_path / f"{prd_id}-{slug}.md")


# ---------- audit_impacts_check unit tests ----------


def test_audit_impacts_check_registered() -> None:
    """audit_impacts_check must be registered in SYSTEM_BUILTINS."""
    assert "audit_impacts_check" in SYSTEM_BUILTINS


def test_audit_impacts_all_present(tmp_path: Path) -> None:
    """Reports clean when all declared impact paths exist."""
    existing = tmp_path / "src" / "foo.py"
    existing.parent.mkdir(parents=True)
    existing.touch()

    prd = _write_and_parse(tmp_path, "PRD-001", "my-feature", impacts=["src/foo.py"])
    ctx = _make_ctx(tmp_path, {"PRD-001": prd})

    audit_impacts_check(ctx)  # should not raise

    assert any("1 path(s) checked" in line for line in ctx.report)
    assert any("0 missing" in line for line in ctx.report)
    # No "Missing" section in report
    assert not any("Missing" in line for line in ctx.report)


def test_audit_impacts_missing_path(tmp_path: Path) -> None:
    """Reports missing paths and raises ValueError."""
    prd = _write_and_parse(
        tmp_path, "PRD-002", "missing-file", impacts=["src/nonexistent.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-002": prd})

    with pytest.raises(ValueError, match="1 declared impact path"):
        audit_impacts_check(ctx)

    assert any("1 missing" in line for line in ctx.report)
    assert any(
        "PRD-002" in line and "src/nonexistent.py" in line for line in ctx.report
    )


def test_audit_impacts_empty_impacts(tmp_path: Path) -> None:
    """PRDs with empty impacts lists are handled without errors."""
    prd = _write_and_parse(tmp_path, "PRD-003", "no-impacts", impacts=[])
    ctx = _make_ctx(tmp_path, {"PRD-003": prd})

    audit_impacts_check(ctx)  # should not raise

    assert any("0 path(s) checked" in line for line in ctx.report)


def test_audit_impacts_no_impacts_field(tmp_path: Path) -> None:
    """PRDs without any impacts field are handled without errors."""
    prd = _write_and_parse(tmp_path, "PRD-004", "null-impacts")
    # impacts defaults to [] from write_prd
    ctx = _make_ctx(tmp_path, {"PRD-004": prd})

    audit_impacts_check(ctx)  # should not raise

    assert any("0 path(s) checked" in line for line in ctx.report)


def test_audit_impacts_mixed(tmp_path: Path) -> None:
    """Reports only the missing paths, not the present ones."""
    present = tmp_path / "present.py"
    present.touch()

    prd = _write_and_parse(
        tmp_path,
        "PRD-005",
        "mixed",
        impacts=["present.py", "absent.py"],
    )
    ctx = _make_ctx(tmp_path, {"PRD-005": prd})

    with pytest.raises(ValueError):
        audit_impacts_check(ctx)

    assert any("2 path(s) checked" in line for line in ctx.report)
    assert any("1 missing" in line for line in ctx.report)
    report_text = "\n".join(ctx.report)
    assert "absent.py" in report_text
    assert "PRD-005" in report_text


def test_audit_impacts_multiple_prds(tmp_path: Path) -> None:
    """Groups missing paths by PRD in the report."""
    (tmp_path / "exists.py").touch()

    prd_a = _write_and_parse(
        tmp_path, "PRD-010", "a", impacts=["exists.py", "missing_a.py"]
    )
    prd_b = _write_and_parse(tmp_path, "PRD-011", "b", impacts=["missing_b.py"])
    ctx = _make_ctx(tmp_path, {"PRD-010": prd_a, "PRD-011": prd_b})

    with pytest.raises(ValueError, match="2 declared impact path"):
        audit_impacts_check(ctx)

    report_text = "\n".join(ctx.report)
    assert "PRD-010" in report_text
    assert "missing_a.py" in report_text
    assert "PRD-011" in report_text
    assert "missing_b.py" in report_text


def test_audit_impacts_dry_run_still_checks(tmp_path: Path) -> None:
    """dry_run=True does not suppress the check — operation is read-only."""
    prd = _write_and_parse(tmp_path, "PRD-006", "dry-run", impacts=["ghost.py"])
    ctx = _make_ctx(tmp_path, {"PRD-006": prd}, dry_run=True)

    with pytest.raises(ValueError):
        audit_impacts_check(ctx)

    assert any("1 missing" in line for line in ctx.report)


# ---------- operation discovery tests ----------


def test_operation_loads_correctly(tmp_path: Path) -> None:
    """audit-impacts operation is discoverable via load_operations."""
    # The real operation.py lives in .darkfactory/operations/audit-impacts/
    # Locate it relative to this test file.
    repo_root = Path(__file__).resolve().parents[1]
    ops_dir = repo_root / ".darkfactory" / "operations"

    operations = load_operations(ops_dir)
    assert "audit-impacts" in operations

    op = operations["audit-impacts"]
    assert op.creates_pr is False
    assert op.requires_clean_main is False
    assert len(op.tasks) == 1


def test_operation_via_runner_clean(tmp_path: Path) -> None:
    """Operation returns success when all impact paths exist."""
    existing = tmp_path / "src" / "foo.py"
    existing.parent.mkdir(parents=True)
    existing.touch()

    from darkfactory.workflow import BuiltIn

    op = SystemOperation(
        name="audit-impacts",
        description="test",
        tasks=[BuiltIn("audit_impacts_check")],
    )
    prd = _write_and_parse(tmp_path, "PRD-020", "ok", impacts=["src/foo.py"])
    ctx = SystemContext(
        repo_root=tmp_path,
        prds={"PRD-020": prd},
        operation=op,
        cwd=tmp_path,
        dry_run=False,
    )

    from darkfactory.system_runner import SYSTEM_BUILTINS as runner_builtins

    assert "audit_impacts_check" in runner_builtins

    result = run_system_operation(op, ctx)
    assert result.success is True
    assert any("0 missing" in line for line in ctx.report)


def test_operation_via_runner_missing(tmp_path: Path) -> None:
    """Operation returns failure when impact paths are missing."""
    from darkfactory.workflow import BuiltIn

    op = SystemOperation(
        name="audit-impacts",
        description="test",
        tasks=[BuiltIn("audit_impacts_check")],
    )
    prd = _write_and_parse(tmp_path, "PRD-021", "missing", impacts=["ghost.py"])
    ctx = SystemContext(
        repo_root=tmp_path,
        prds={"PRD-021": prd},
        operation=op,
        cwd=tmp_path,
        dry_run=False,
    )

    result = run_system_operation(op, ctx)
    assert result.success is False
    assert "1 missing" in "\n".join(ctx.report)
