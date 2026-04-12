"""Tests for the audit-impacts system operation and its audit_impacts_check builtin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from darkfactory.operations.project_builtins import (
    SYSTEM_BUILTINS,
    audit_impacts_check,
)
from darkfactory.loader import load_operations
from darkfactory.model import PRD, parse_prd
from darkfactory.project import ProjectContext, ProjectOperation
from darkfactory.runner import run_project_operation

from tests.conftest import write_prd


# ---------- helpers ----------


def _make_op() -> ProjectOperation:
    return ProjectOperation(name="test-op", description="test", tasks=[])


def _make_ctx(
    tmp_path: Path,
    prds: dict[str, PRD] | None = None,
    *,
    dry_run: bool = False,
) -> ProjectContext:
    return ProjectContext(
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

    prd = _write_and_parse(
        tmp_path, "PRD-001", "my-feature", status="done", impacts=["src/foo.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-001": prd})

    audit_impacts_check(ctx)  # should not raise

    assert any("1 path(s) checked" in line for line in ctx.report)
    assert any("0 error(s)" in line for line in ctx.report)
    assert not any("ERRORS" in line for line in ctx.report)
    assert not any("WARNINGS" in line for line in ctx.report)


def test_audit_impacts_missing_on_done_prd(tmp_path: Path) -> None:
    """Missing paths on done PRDs are errors and raise ValueError."""
    prd = _write_and_parse(
        tmp_path,
        "PRD-002",
        "missing-file",
        status="done",
        impacts=["src/nonexistent.py"],
    )
    ctx = _make_ctx(tmp_path, {"PRD-002": prd})

    with pytest.raises(ValueError, match="1 declared impact path"):
        audit_impacts_check(ctx)

    assert any("1 error(s)" in line for line in ctx.report)
    assert any(
        "PRD-002" in line and "src/nonexistent.py" in line for line in ctx.report
    )


def test_audit_impacts_missing_on_review_prd(tmp_path: Path) -> None:
    """Missing paths on review PRDs are also errors."""
    prd = _write_and_parse(
        tmp_path, "PRD-030", "review-missing", status="review", impacts=["ghost.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-030": prd})

    with pytest.raises(ValueError, match="1 declared impact path"):
        audit_impacts_check(ctx)

    assert any("ERRORS" in line for line in ctx.report)


def test_audit_impacts_missing_on_ready_prd_is_warning(tmp_path: Path) -> None:
    """Missing paths on ready PRDs are warnings, not errors — no raise."""
    prd = _write_and_parse(
        tmp_path, "PRD-007", "not-started", status="ready", impacts=["src/future.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-007": prd})

    audit_impacts_check(ctx)  # should NOT raise

    assert any("0 error(s)" in line for line in ctx.report)
    assert any("1 warning(s)" in line for line in ctx.report)
    assert any("WARNINGS" in line for line in ctx.report)


def test_audit_impacts_missing_on_draft_prd_is_warning(tmp_path: Path) -> None:
    """Missing paths on draft PRDs are warnings, not errors."""
    prd = _write_and_parse(
        tmp_path, "PRD-008", "draft-prd", status="draft", impacts=["src/planned.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-008": prd})

    audit_impacts_check(ctx)  # should NOT raise

    assert any("0 error(s)" in line for line in ctx.report)
    assert any("1 warning(s)" in line for line in ctx.report)


def test_audit_impacts_missing_on_in_progress_prd_is_warning(tmp_path: Path) -> None:
    """Missing paths on in_progress PRDs are warnings, not errors."""
    prd = _write_and_parse(
        tmp_path, "PRD-009", "wip", status="in_progress", impacts=["src/wip.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-009": prd})

    audit_impacts_check(ctx)  # should NOT raise

    assert any("0 error(s)" in line for line in ctx.report)
    assert any("1 warning(s)" in line for line in ctx.report)


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


def test_audit_impacts_mixed_completed_and_incomplete(tmp_path: Path) -> None:
    """Only missing paths on completed PRDs cause errors; incomplete PRDs are warnings."""
    (tmp_path / "exists.py").touch()

    prd_done = _write_and_parse(
        tmp_path,
        "PRD-010",
        "done-missing",
        status="done",
        impacts=["exists.py", "missing_done.py"],
    )
    prd_ready = _write_and_parse(
        tmp_path,
        "PRD-011",
        "ready-missing",
        status="ready",
        impacts=["missing_ready.py"],
    )
    ctx = _make_ctx(tmp_path, {"PRD-010": prd_done, "PRD-011": prd_ready})

    with pytest.raises(ValueError, match="1 declared impact path"):
        audit_impacts_check(ctx)

    report_text = "\n".join(ctx.report)
    assert "1 error(s)" in report_text
    assert "1 warning(s)" in report_text
    assert "missing_done.py" in report_text
    assert "missing_ready.py" in report_text
    assert "ERRORS" in report_text
    assert "WARNINGS" in report_text


def test_audit_impacts_multiple_done_prds(tmp_path: Path) -> None:
    """Groups missing paths by PRD in the report for completed PRDs."""
    prd_a = _write_and_parse(
        tmp_path, "PRD-012", "a", status="done", impacts=["missing_a.py"]
    )
    prd_b = _write_and_parse(
        tmp_path, "PRD-013", "b", status="done", impacts=["missing_b.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-012": prd_a, "PRD-013": prd_b})

    with pytest.raises(ValueError, match="2 declared impact path"):
        audit_impacts_check(ctx)

    report_text = "\n".join(ctx.report)
    assert "PRD-012" in report_text
    assert "missing_a.py" in report_text
    assert "PRD-013" in report_text
    assert "missing_b.py" in report_text


def test_audit_impacts_dry_run_still_checks(tmp_path: Path) -> None:
    """dry_run=True does not suppress the check — operation is read-only."""
    prd = _write_and_parse(
        tmp_path, "PRD-006", "dry-run", status="done", impacts=["ghost.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-006": prd}, dry_run=True)

    with pytest.raises(ValueError):
        audit_impacts_check(ctx)

    assert any("1 error(s)" in line for line in ctx.report)


def test_audit_impacts_report_includes_status(tmp_path: Path) -> None:
    """Report lines include PRD status for context."""
    prd = _write_and_parse(
        tmp_path, "PRD-014", "status-shown", status="done", impacts=["gone.py"]
    )
    ctx = _make_ctx(tmp_path, {"PRD-014": prd})

    with pytest.raises(ValueError):
        audit_impacts_check(ctx)

    assert any("[done]" in line for line in ctx.report)


# ---------- operation discovery tests ----------


def test_operation_loads_correctly(tmp_path: Path) -> None:
    """audit-impacts operation is discoverable via load_operations."""
    # The real operation.py lives in src/darkfactory/workflow/definitions/project/
    # Locate it relative to this test file.
    repo_root = Path(__file__).resolve().parents[1]
    ops_dir = repo_root / "src" / "darkfactory" / "workflow" / "definitions" / "project"

    operations = load_operations(ops_dir, include_builtins=False, include_user=False)
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

    op = ProjectOperation(
        name="audit-impacts",
        description="test",
        tasks=[BuiltIn("audit_impacts_check")],
    )
    prd = _write_and_parse(
        tmp_path, "PRD-020", "ok", status="done", impacts=["src/foo.py"]
    )
    ctx = ProjectContext(
        repo_root=tmp_path,
        prds={"PRD-020": prd},
        operation=op,
        cwd=tmp_path,
        dry_run=False,
    )

    from darkfactory.operations.project_builtins import (
        SYSTEM_BUILTINS as runner_builtins,
    )

    assert "audit_impacts_check" in runner_builtins

    result = run_project_operation(op, ctx)
    assert result.success is True
    assert any("0 error(s)" in line for line in ctx.report)


def test_operation_via_runner_missing(tmp_path: Path) -> None:
    """Operation returns failure when completed PRDs have missing impact paths."""
    from darkfactory.workflow import BuiltIn

    op = ProjectOperation(
        name="audit-impacts",
        description="test",
        tasks=[BuiltIn("audit_impacts_check")],
    )
    prd = _write_and_parse(
        tmp_path, "PRD-021", "missing", status="done", impacts=["ghost.py"]
    )
    ctx = ProjectContext(
        repo_root=tmp_path,
        prds={"PRD-021": prd},
        operation=op,
        cwd=tmp_path,
        dry_run=False,
    )

    result = run_project_operation(op, ctx)
    assert result.success is False
    assert "1 error(s)" in "\n".join(ctx.report)


def test_operation_via_runner_warning_only(tmp_path: Path) -> None:
    """Operation returns success when only incomplete PRDs have missing impacts."""
    from darkfactory.workflow import BuiltIn

    op = ProjectOperation(
        name="audit-impacts",
        description="test",
        tasks=[BuiltIn("audit_impacts_check")],
    )
    prd = _write_and_parse(
        tmp_path, "PRD-022", "ready-warn", status="ready", impacts=["future.py"]
    )
    ctx = ProjectContext(
        repo_root=tmp_path,
        prds={"PRD-022": prd},
        operation=op,
        cwd=tmp_path,
        dry_run=False,
    )

    result = run_project_operation(op, ctx)
    assert result.success is True
    assert "1 warning(s)" in "\n".join(ctx.report)
