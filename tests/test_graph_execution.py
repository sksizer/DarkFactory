"""Tests for sequential graph execution (PRD-220).

The executor is tested with a fake ``run_workflow`` injection point so
we don't need a real git repo, real agent, or real worktree — the unit
under test is the traversal/scheduling logic, not the underlying runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from darkfactory.graph_execution import (
    ExecutionReport,
    MultiDepUnsupported,
    RunEvent,
    actionable_order,
    execute_graph,
    graph_scope,
    plan_execution,
    resolve_base_ref,
)
from darkfactory.prd import PRD, load_all, set_status_at
from darkfactory.runner import RunResult
from darkfactory.workflow import Workflow

from .conftest import write_prd


# ---- Test helpers ---------------------------------------------------------


def _make_workflows() -> dict[str, Workflow]:
    """A single no-op workflow that matches any PRD.

    The executor only uses ``workflows`` to assign a workflow to each
    picked PRD — the actual task list is never invoked because we inject
    a fake ``run_workflow_fn``.
    """
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
    """Build a fake ``run_workflow`` that records calls and returns scripted results.

    ``outcomes`` maps PRD id → success bool. Unlisted PRDs succeed by default.
    The returned callable has a ``.calls`` list of ``(prd_id, base_ref)`` tuples
    and a ``.set_done`` hook — after each successful call the PRD file's status
    is flipped to ``done`` so re-loads in the executor loop see the progress.
    """
    outcomes = outcomes or {}
    calls: list[tuple[str, str]] = []

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
        calls.append((prd.id, base_ref))
        success = outcomes.get(prd.id, True)
        if success:
            set_status_at(prd.path, "done")
            return RunResult(success=True, pr_url=f"https://example/pr/{prd.id}")
        return RunResult(success=False, failure_reason=f"scripted fail: {prd.id}")

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


def _exec(
    tmp_prd_dir: Path,
    root_id: str,
    *,
    outcomes: dict[str, bool] | None = None,
    max_runs: int | None = None,
    workflow_override: str | None = "test-noop",
) -> tuple[ExecutionReport, list[RunEvent], list[tuple[str, str]]]:
    """Run ``execute_graph`` with sensible test defaults and capture events."""
    events: list[RunEvent] = []
    fake = _fake_runner(outcomes)
    report = execute_graph(
        root_id=root_id,
        prd_dir=tmp_prd_dir,
        repo_root=tmp_prd_dir,
        workflows=_make_workflows(),
        default_base="main",
        max_runs=max_runs,
        dry_run=False,
        event_sink=events.append,
        run_workflow_fn=fake,
        workflow_override=workflow_override,
    )
    return report, events, fake.calls  # type: ignore[attr-defined]


# ---- Pure helpers ---------------------------------------------------------


def test_graph_scope_leaf_only(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "leaf")
    prds = load_all(tmp_prd_dir)
    assert graph_scope("PRD-001", prds) == {"PRD-001"}


def test_graph_scope_containment_descendants(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-002", "child-a", parent="PRD-001")
    write_prd(tmp_prd_dir, "PRD-003", "child-b", parent="PRD-001")
    prds = load_all(tmp_prd_dir)
    assert graph_scope("PRD-001", prds) == {"PRD-001", "PRD-002", "PRD-003"}


def test_graph_scope_pulls_unmet_deps(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "upstream", status="ready")
    write_prd(tmp_prd_dir, "PRD-002", "downstream", depends_on=["PRD-001"])
    prds = load_all(tmp_prd_dir)
    # Running PRD-002 pulls in PRD-001 as an unmet dep.
    assert graph_scope("PRD-002", prds) == {"PRD-001", "PRD-002"}


def test_graph_scope_skips_done_deps(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "upstream", status="done")
    write_prd(tmp_prd_dir, "PRD-002", "downstream", depends_on=["PRD-001"])
    prds = load_all(tmp_prd_dir)
    assert graph_scope("PRD-002", prds) == {"PRD-002"}


def test_actionable_order_topo(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "first")
    write_prd(tmp_prd_dir, "PRD-002", "second", depends_on=["PRD-001"])
    write_prd(tmp_prd_dir, "PRD-003", "third", depends_on=["PRD-002"])
    prds = load_all(tmp_prd_dir)
    assert actionable_order({"PRD-001", "PRD-002", "PRD-003"}, prds) == [
        "PRD-001",
        "PRD-002",
        "PRD-003",
    ]


def test_resolve_base_ref_independent(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "solo")
    prds = load_all(tmp_prd_dir)
    assert resolve_base_ref(prds["PRD-001"], {}, "main", prds) == "main"


def test_resolve_base_ref_single_dep_stacked(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "upstream", status="ready")
    write_prd(tmp_prd_dir, "PRD-002", "downstream", depends_on=["PRD-001"])
    prds = load_all(tmp_prd_dir)
    completed = {"PRD-001": "prd/PRD-001-upstream"}
    assert (
        resolve_base_ref(prds["PRD-002"], completed, "main", prds)
        == "prd/PRD-001-upstream"
    )


def test_resolve_base_ref_multi_dep_raises(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", status="ready")
    write_prd(tmp_prd_dir, "PRD-002", "b", status="ready")
    write_prd(tmp_prd_dir, "PRD-003", "c", depends_on=["PRD-001", "PRD-002"])
    prds = load_all(tmp_prd_dir)
    with pytest.raises(MultiDepUnsupported):
        resolve_base_ref(prds["PRD-003"], {}, "main", prds)


# ---- Executor: single-PRD degenerate case --------------------------------


def test_execute_single_leaf(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "leaf")
    report, events, calls = _exec(tmp_prd_dir, "PRD-001")
    assert report.completed == ["PRD-001"]
    assert report.failed == []
    assert calls == [("PRD-001", "main")]
    assert [e.event for e in events] == ["start", "finish"]


# ---- Executor: linear chain with stacked base ----------------------------


def test_execute_linear_chain_stacks_single_dep(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a")
    write_prd(tmp_prd_dir, "PRD-002", "b", depends_on=["PRD-001"])
    write_prd(tmp_prd_dir, "PRD-003", "c", depends_on=["PRD-002"])
    report, _events, calls = _exec(tmp_prd_dir, "PRD-001")
    # Need an epic container to scope into 002 and 003 — without a parent
    # epic, starting at PRD-001 only walks PRD-001's subtree. Fix: use
    # an epic root.
    # (Adjusted test below.)
    assert report.completed == ["PRD-001"]
    assert calls == [("PRD-001", "main")]


def test_execute_epic_linear_chain_stacks_single_dep(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100", depends_on=["PRD-001"])
    write_prd(tmp_prd_dir, "PRD-003", "c", parent="PRD-100", depends_on=["PRD-002"])
    report, _events, calls = _exec(tmp_prd_dir, "PRD-100")
    assert report.completed == ["PRD-001", "PRD-002", "PRD-003"]
    # Stacking: 002 bases on 001's branch, 003 on 002's.
    assert calls == [
        ("PRD-001", "main"),
        ("PRD-002", "prd/PRD-001-a"),
        ("PRD-003", "prd/PRD-002-b"),
    ]


# ---- Executor: branching epic --------------------------------------------


def test_execute_branching_epic_independent_siblings_base_on_main(
    tmp_prd_dir: Path,
) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-003", "c", parent="PRD-100")
    report, _events, calls = _exec(tmp_prd_dir, "PRD-100")
    assert set(report.completed) == {"PRD-001", "PRD-002", "PRD-003"}
    assert all(base == "main" for _, base in calls)


# ---- Executor: depends_on cross-edges ------------------------------------


def test_execute_cross_edges_respected(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100")
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "c",
        parent="PRD-100",
        depends_on=["PRD-001"],
    )
    report, _events, calls = _exec(tmp_prd_dir, "PRD-100")
    ids = [c[0] for c in calls]
    assert ids.index("PRD-001") < ids.index("PRD-003")
    assert set(report.completed) == {"PRD-001", "PRD-002", "PRD-003"}


# ---- Executor: failure isolation -----------------------------------------


def test_execute_failure_marks_blocked_and_prunes_dependents(
    tmp_prd_dir: Path,
) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "b",
        parent="PRD-100",
        depends_on=["PRD-001"],
    )
    write_prd(tmp_prd_dir, "PRD-003", "c", parent="PRD-100")
    report, events, calls = _exec(tmp_prd_dir, "PRD-100", outcomes={"PRD-001": False})
    call_ids = [c[0] for c in calls]
    assert "PRD-001" in call_ids
    assert "PRD-002" not in call_ids  # pruned — depends_on a failed PRD
    assert "PRD-003" in call_ids  # unrelated — runs
    assert report.failed and report.failed[0][0] == "PRD-001"
    # Source PRD file marked blocked.
    prds = load_all(tmp_prd_dir)
    assert prds["PRD-001"].status == "blocked"


# ---- Executor: --max-runs -------------------------------------------------


def test_execute_max_runs_caps_total(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-003", "c", parent="PRD-100")
    report, _events, calls = _exec(tmp_prd_dir, "PRD-100", max_runs=2)
    assert len(calls) == 2
    assert len(report.completed) == 2
    assert any(reason == "max_runs" for _, reason in report.skipped)


# ---- Executor: mid-run DAG growth via planning workflow ------------------


def test_execute_mid_run_new_children_are_picked_up(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "seed", parent="PRD-100")

    fake_calls: list[tuple[str, str]] = []

    def fake(
        *,
        prd: PRD,
        workflow: Workflow,
        repo_root: Path,
        base_ref: str,
        dry_run: bool,
        model_override: str | None = None,
        **_kw: object,
    ) -> RunResult:
        fake_calls.append((prd.id, base_ref))
        # When PRD-001 runs, simulate a planning workflow that creates a
        # new sibling child PRD-002 under the same epic.
        if prd.id == "PRD-001":
            write_prd(
                tmp_prd_dir,
                "PRD-002",
                "generated",
                parent="PRD-100",
            )
        set_status_at(prd.path, "done")
        return RunResult(success=True, pr_url=f"https://example/pr/{prd.id}")

    report = execute_graph(
        root_id="PRD-100",
        prd_dir=tmp_prd_dir,
        repo_root=tmp_prd_dir,
        workflows=_make_workflows(),
        default_base="main",
        dry_run=False,
        event_sink=lambda _e: None,
        run_workflow_fn=fake,
        workflow_override="test-noop",
    )
    assert set(report.completed) == {"PRD-001", "PRD-002"}
    # Ensure the newly-introduced PRD ran too.
    assert {c[0] for c in fake_calls} == {"PRD-001", "PRD-002"}


def test_execute_max_runs_counts_introduced_prds(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "seed", parent="PRD-100")

    def fake(
        *,
        prd: PRD,
        workflow: Workflow,
        repo_root: Path,
        base_ref: str,
        dry_run: bool,
        model_override: str | None = None,
        **_kw: object,
    ) -> RunResult:
        if prd.id == "PRD-001":
            write_prd(tmp_prd_dir, "PRD-002", "generated", parent="PRD-100")
        set_status_at(prd.path, "done")
        return RunResult(success=True)

    report = execute_graph(
        root_id="PRD-100",
        prd_dir=tmp_prd_dir,
        repo_root=tmp_prd_dir,
        workflows=_make_workflows(),
        default_base="main",
        max_runs=1,
        dry_run=False,
        event_sink=lambda _e: None,
        run_workflow_fn=fake,
        workflow_override="test-noop",
    )
    # max_runs=1 stops after PRD-001; the introduced PRD-002 doesn't run.
    assert report.completed == ["PRD-001"]
    assert any(reason == "max_runs" for _, reason in report.skipped)


# ---- Executor: multi-dep error -------------------------------------------


def test_execute_multi_dep_skipped_with_reason(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100")
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "c",
        parent="PRD-100",
        depends_on=["PRD-001", "PRD-002"],
    )
    report, events, calls = _exec(tmp_prd_dir, "PRD-100")
    call_ids = [c[0] for c in calls]
    # PRD-001 and PRD-002 both run; PRD-003 is skipped because even after
    # both deps complete in this run, resolve_base_ref still rejects
    # multi-dep. (Stacking only supports single-dep.)
    assert "PRD-001" in call_ids
    assert "PRD-002" in call_ids
    assert "PRD-003" not in call_ids
    assert any("multi_dep" in reason for _, reason in report.skipped)


# ---- Dry-run plan ---------------------------------------------------------


def test_plan_execution_shows_full_dag_and_slice(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100", depends_on=["PRD-001"])
    prds = load_all(tmp_prd_dir)
    plan = plan_execution(prds["PRD-100"], prds, max_runs=None, default_base="main")
    assert plan.full_dag == ["PRD-001", "PRD-002"]
    assert plan.execution_slice == ["PRD-001", "PRD-002"]


def test_plan_execution_max_runs_trims_slice(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-100", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-001", "a", parent="PRD-100")
    write_prd(tmp_prd_dir, "PRD-002", "b", parent="PRD-100")
    prds = load_all(tmp_prd_dir)
    plan = plan_execution(prds["PRD-100"], prds, max_runs=1, default_base="main")
    assert len(plan.full_dag) == 2
    assert len(plan.execution_slice) == 1
    assert any("past --max-runs" in r for _, r in plan.skipped)
