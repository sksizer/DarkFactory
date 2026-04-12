"""Tests for the drain-ready-queue execution mode (PRD-563.5).

Covers ``discover_ready_queue``, ``matches_filters``, ``QueueStrategy``
through ``execute_graph``, and CLI validation.

Tests use the injectable ``run_workflow_fn`` pattern — no real workflows
are invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest

from darkfactory.graph import (
    ExecutionReport,
    QueueFilters,
    QueueStrategy,
    discover_ready_queue,
    execute_graph,
    matches_filters,
)
from darkfactory.model import PRD, load_all, set_status_at
from darkfactory.runner import RunResult
from darkfactory.workflow import Workflow

from .conftest import write_prd


# ---- Helpers ----------------------------------------------------------------


def _write_tagged_prd(
    dir_path: Path,
    prd_id: str,
    slug: str,
    *,
    status: str = "ready",
    priority: str = "medium",
    depends_on: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Write a PRD with optional tags to ``dir_path``."""
    fm_lines = [
        "---",
        f'id: "{prd_id}"',
        f'title: "Test {prd_id}"',
        "kind: task",
        f"status: {status}",
        f"priority: {priority}",
        "effort: s",
        "capability: simple",
        "parent: null",
    ]
    if depends_on:
        fm_lines.append("depends_on:")
        for dep in depends_on:
            fm_lines.append(f'  - "[[{dep}-stub]]"')
    else:
        fm_lines.append("depends_on: []")
    fm_lines.append("blocks: []")
    fm_lines.append("impacts: []")
    fm_lines.append("workflow: null")
    fm_lines.append("created: 2026-04-09")
    fm_lines.append("updated: 2026-04-09")
    if tags:
        fm_lines.append("tags:")
        for t in tags:
            fm_lines.append(f"  - {t}")
    else:
        fm_lines.append("tags: []")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append("# Test\n\nBody.\n")

    path = dir_path / f"{prd_id}-{slug}.md"
    path.write_text("\n".join(fm_lines), encoding="utf-8")
    return path


def _make_workflows() -> dict[str, Workflow]:
    wf = Workflow(
        name="test-noop",
        description="no-op test workflow",
        priority=0,
        tasks=[],
    )
    return {"test-noop": wf}


def _fake_runner(
    outcomes: dict[str, bool] | None = None,
) -> Callable[..., RunResult]:
    """Build a fake ``run_workflow`` that records calls and returns scripted results."""
    outcomes = outcomes or {}
    calls: list[str] = []

    def fake(
        *,
        prd: PRD,
        workflow: Workflow,
        repo_root: Path,
        base_ref: str,
        dry_run: bool,
        model_override: str | None = None,
        **_kwargs: object,
    ) -> RunResult:
        calls.append(prd.id)
        success = outcomes.get(prd.id, True)
        if success:
            set_status_at(prd.path, "done")
            return RunResult(success=True, pr_url=f"https://example/pr/{prd.id}")
        return RunResult(success=False, failure_reason=f"scripted fail: {prd.id}")

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


def _exec_queue(
    tmp_data_dir: Path,
    filters: QueueFilters | None = None,
    *,
    outcomes: dict[str, bool] | None = None,
    max_runs: int | None = None,
) -> tuple[ExecutionReport, list[str]]:
    """Run ``execute_graph`` in queue mode and return (report, call_ids)."""
    if filters is None:
        filters = QueueFilters()
    fake = _fake_runner(outcomes)
    report = execute_graph(
        strategy=QueueStrategy(filters),
        data_dir=tmp_data_dir,
        repo_root=tmp_data_dir,
        workflows=_make_workflows(),
        default_base="main",
        max_runs=max_runs,
        dry_run=False,
        event_sink=None,
        run_workflow_fn=fake,
        workflow_override="test-noop",
    )
    return report, fake.calls  # type: ignore[attr-defined]


# ---- TestDiscoverReadyQueue -------------------------------------------------


class TestDiscoverReadyQueue:
    def test_empty_set(self, tmp_data_dir: Path) -> None:
        prds = load_all(tmp_data_dir)
        result = discover_ready_queue(prds, QueueFilters())
        assert result == []

    def test_single_ready(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "solo")
        prds = load_all(tmp_data_dir)
        result = discover_ready_queue(prds, QueueFilters())
        assert [p.id for p in result] == ["PRD-001"]

    def test_priority_ordering(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "low-prd", priority="low")
        write_prd(tmp_data_dir / "prds", "PRD-002", "high-prd", priority="high")
        write_prd(tmp_data_dir / "prds", "PRD-003", "medium-prd", priority="medium")
        prds = load_all(tmp_data_dir)
        result = discover_ready_queue(prds, QueueFilters())
        ids = [p.id for p in result]
        # high before medium before low
        assert ids.index("PRD-002") < ids.index("PRD-003")
        assert ids.index("PRD-003") < ids.index("PRD-001")

    def test_unsatisfied_dep_excluded(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "dep", status="draft")
        write_prd(
            tmp_data_dir / "prds", "PRD-002", "downstream", depends_on=["PRD-001"]
        )
        prds = load_all(tmp_data_dir)
        result = discover_ready_queue(prds, QueueFilters())
        ids = [p.id for p in result]
        assert "PRD-002" not in ids  # dep not satisfied

    def test_review_dep_satisfied(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "dep", status="review")
        write_prd(
            tmp_data_dir / "prds", "PRD-002", "downstream", depends_on=["PRD-001"]
        )
        prds = load_all(tmp_data_dir)
        result = discover_ready_queue(prds, QueueFilters())
        ids = [p.id for p in result]
        # review counts as satisfied
        assert "PRD-002" in ids


# ---- TestMatchesFilters -----------------------------------------------------


class TestMatchesFilters:
    def _load_prd(
        self,
        tmp_data_dir: Path,
        prd_id: str,
        slug: str,
        **kwargs: object,
    ) -> PRD:
        _write_tagged_prd(tmp_data_dir / "prds", prd_id, slug, **kwargs)  # type: ignore[arg-type]
        prds = load_all(tmp_data_dir)
        return prds[prd_id]

    def test_priority_filter_excludes_low(self, tmp_data_dir: Path) -> None:
        high_prd = self._load_prd(tmp_data_dir, "PRD-001", "high", priority="high")
        med_prd = self._load_prd(tmp_data_dir, "PRD-002", "med", priority="medium")
        low_prd = self._load_prd(tmp_data_dir, "PRD-003", "low", priority="low")
        filters = QueueFilters(min_priority="high")
        assert matches_filters(high_prd, filters) is True
        assert matches_filters(med_prd, filters) is False
        assert matches_filters(low_prd, filters) is False

    def test_tag_filter_includes_match(self, tmp_data_dir: Path) -> None:
        tagged = self._load_prd(tmp_data_dir, "PRD-001", "tagged", tags=["harness"])
        untagged = self._load_prd(tmp_data_dir, "PRD-002", "untagged", tags=[])
        filters = QueueFilters(tags=["harness"])
        assert matches_filters(tagged, filters) is True
        assert matches_filters(untagged, filters) is False

    def test_tag_or_semantics(self, tmp_data_dir: Path) -> None:
        prd_a = self._load_prd(tmp_data_dir, "PRD-001", "a", tags=["alpha"])
        prd_b = self._load_prd(tmp_data_dir, "PRD-002", "b", tags=["beta"])
        prd_c = self._load_prd(tmp_data_dir, "PRD-003", "c", tags=["other"])
        filters = QueueFilters(tags=["alpha", "beta"])
        assert matches_filters(prd_a, filters) is True
        assert matches_filters(prd_b, filters) is True
        assert matches_filters(prd_c, filters) is False

    def test_exclude(self, tmp_data_dir: Path) -> None:
        prd = self._load_prd(tmp_data_dir, "PRD-005", "excluded")
        other = self._load_prd(tmp_data_dir, "PRD-006", "other")
        filters = QueueFilters(exclude_ids=["PRD-005"])
        assert matches_filters(prd, filters) is False
        assert matches_filters(other, filters) is True

    def test_empty_filters_pass_all(self, tmp_data_dir: Path) -> None:
        prd = self._load_prd(tmp_data_dir, "PRD-001", "any", priority="low", tags=[])
        assert matches_filters(prd, QueueFilters()) is True


# ---- TestQueueExecution -----------------------------------------------------


class TestQueueExecution:
    def test_single_prd(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "solo")
        report, calls = _exec_queue(tmp_data_dir)
        assert calls == ["PRD-001"]
        assert report.completed == ["PRD-001"]
        assert report.failed == []

    def test_priority_order(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "low", priority="low")
        write_prd(tmp_data_dir / "prds", "PRD-002", "high", priority="high")
        write_prd(tmp_data_dir / "prds", "PRD-003", "medium", priority="medium")
        report, calls = _exec_queue(tmp_data_dir)
        # high runs first, then medium, then low
        assert calls.index("PRD-002") < calls.index("PRD-003")
        assert calls.index("PRD-003") < calls.index("PRD-001")
        assert set(report.completed) == {"PRD-001", "PRD-002", "PRD-003"}

    def test_dependency_chain(self, tmp_data_dir: Path) -> None:
        # A depends on B: B must run first
        write_prd(tmp_data_dir / "prds", "PRD-001", "b")
        write_prd(tmp_data_dir / "prds", "PRD-002", "a", depends_on=["PRD-001"])
        report, calls = _exec_queue(tmp_data_dir)
        assert calls.index("PRD-001") < calls.index("PRD-002")
        assert set(report.completed) == {"PRD-001", "PRD-002"}

    def test_mid_run_unlock(self, tmp_data_dir: Path) -> None:
        # PRD-002 depends on PRD-001 which is not initially in the ready queue
        # (status blocked), but after PRD-001 completes it becomes visible.
        # We simulate this by starting PRD-001 as ready and PRD-002 as
        # depending on it — the queue loop should re-discover PRD-002 after
        # PRD-001 completes.
        write_prd(tmp_data_dir / "prds", "PRD-001", "first")
        write_prd(tmp_data_dir / "prds", "PRD-002", "second", depends_on=["PRD-001"])
        # PRD-002 is not in the initial queue because PRD-001 is not done yet.
        prds = load_all(tmp_data_dir)
        initial = discover_ready_queue(prds, QueueFilters())
        assert [p.id for p in initial] == ["PRD-001"]
        # After full execution both should complete.
        report, calls = _exec_queue(tmp_data_dir)
        assert "PRD-001" in calls
        assert "PRD-002" in calls
        assert calls.index("PRD-001") < calls.index("PRD-002")

    def test_max_runs_cutoff(self, tmp_data_dir: Path) -> None:
        write_prd(tmp_data_dir / "prds", "PRD-001", "a")
        write_prd(tmp_data_dir / "prds", "PRD-002", "b")
        write_prd(tmp_data_dir / "prds", "PRD-003", "c")
        report, calls = _exec_queue(tmp_data_dir, max_runs=2)
        assert len(calls) == 2
        assert len(report.completed) == 2
        assert any(reason == "max_runs" for _, reason in report.skipped)

    def test_failure_isolation(self, tmp_data_dir: Path) -> None:
        # PRD-001 fails; PRD-002 depends on it (should be skipped);
        # PRD-003 is unrelated (should succeed).
        write_prd(tmp_data_dir / "prds", "PRD-001", "fails")
        write_prd(
            tmp_data_dir / "prds", "PRD-002", "blocked-by-001", depends_on=["PRD-001"]
        )
        write_prd(tmp_data_dir / "prds", "PRD-003", "unrelated")
        report, calls = _exec_queue(tmp_data_dir, outcomes={"PRD-001": False})
        assert "PRD-001" in calls
        assert "PRD-002" not in calls  # pruned because PRD-001 failed
        assert "PRD-003" in calls  # unrelated — runs fine
        assert report.failed and report.failed[0][0] == "PRD-001"
        # PRD-001 should be marked blocked in the file
        prds = load_all(tmp_data_dir)
        assert prds["PRD-001"].status == "blocked"


# ---- TestCLIValidation ------------------------------------------------------


class TestCLIValidation:
    """Test CLI argument validation for `prd run` in queue mode."""

    @staticmethod
    def _setup_project(tmp_path: Path) -> Path:
        """Create .darkfactory/ layout with .git and return the prds dir."""
        (tmp_path / ".git").mkdir(exist_ok=True)
        df = tmp_path / ".darkfactory"
        df.mkdir()
        prds = df / "data" / "prds"
        prds.mkdir(parents=True)
        (df / "data" / "archive").mkdir()
        (df / "workflows").mkdir()
        return prds

    def _run_main(self, argv: list[str]) -> tuple[int, str]:
        """Invoke the CLI main() and capture stderr output."""
        import io

        from darkfactory.cli import main

        captured_stderr = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            exit_code = main(argv)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        finally:
            sys.stderr = old_stderr
        return exit_code, captured_stderr.getvalue()

    def test_all_and_prd_id_error(self, tmp_path: Path) -> None:
        prd_dir = self._setup_project(tmp_path)
        write_prd(prd_dir, "PRD-001", "task")

        exit_code, stderr = self._run_main(
            [
                "--directory",
                str(tmp_path),
                "run",
                "--all",
                "PRD-001",
            ]
        )
        assert exit_code != 0
        assert "mutually exclusive" in stderr or "--all" in stderr

    def test_neither_error(self, tmp_path: Path) -> None:
        self._setup_project(tmp_path)

        exit_code, stderr = self._run_main(
            [
                "--directory",
                str(tmp_path),
                "run",
            ]
        )
        assert exit_code != 0
        assert "PRD ID" in stderr or "--all" in stderr or "provide" in stderr

    def test_filter_args_parse(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--all --priority high --tag harness --exclude PRD-99 parses correctly."""
        from darkfactory.cli._parser import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "--directory",
                str(tmp_path),
                "run",
                "--all",
                "--priority",
                "high",
                "--tag",
                "harness",
                "--exclude",
                "PRD-99",
            ]
        )
        assert args.run_all is True
        assert args.priority == "high"
        assert args.tags == ["harness"]
        assert args.exclude_ids == ["PRD-99"]
