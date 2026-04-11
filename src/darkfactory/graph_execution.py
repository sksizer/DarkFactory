"""Sequential graph execution for PRD runs.

Walks a DAG rooted at a given PRD and runs each actionable leaf in
topological order, respecting ``depends_on`` edges and containment. This
is the engine behind ``prd run <epic>`` — single-PRD execution is just
the degenerate case of a 1-element traversal.

Scope (PRD-220):

- **Sequential only.** Parallel execution is PRD-551.
- **Single-dep stacking.** A PRD with exactly one dependency that was
  completed during this invocation has its worktree based on that
  dependency's branch. Independent siblings base on ``default_base``.
- **Multi-dep error.** A PRD with ≥2 unmerged dependencies is skipped
  with a pointer to PRD-552.
- **Failure isolation.** A failed PRD is marked ``blocked`` and its
  transitive dependents are skipped; unrelated branches continue.
- **Mid-run DAG growth.** After each run, PRDs are re-loaded so any
  new children created by a planning workflow are picked up. Newly-
  introduced PRDs count against ``--max-runs``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from .style import Styler

from . import assign, containment, graph
from .event_log import EventWriter
from .model import PRD, load_all, set_status_at
from .runner import RunResult, _compute_branch_name, run_workflow
from .workflow import Workflow

logger = logging.getLogger("darkfactory.graph_execution")


# ---- Event stream ---------------------------------------------------------


@dataclass
class RunEvent:
    """A single event in the graph execution stream.

    Events are emitted as PRDs start, finish, or are skipped. They are
    designed to be serialized to JSON for ``--json`` consumers (see also
    PRD-550, which will consume the ``changed_files`` field to flag stale
    downstream PRDs).
    """

    event: str  # "plan" | "start" | "finish" | "skip"
    prd_id: str
    reason: str = ""
    success: bool | None = None
    base_ref: str | None = None
    pr_url: str | None = None
    failure_reason: str | None = None
    # Populated on "finish" — files this PRD's run actually changed. PRD-550
    # consumes this to flag downstream PRDs whose declared impacts overlap.
    changed_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"event": self.event, "prd_id": self.prd_id}
        if self.reason:
            out["reason"] = self.reason
        if self.success is not None:
            out["success"] = self.success
        if self.base_ref:
            out["base_ref"] = self.base_ref
        if self.pr_url:
            out["pr_url"] = self.pr_url
        if self.failure_reason:
            out["failure_reason"] = self.failure_reason
        if self.changed_files:
            out["changed_files"] = self.changed_files
        return out


EventSink = Callable[[RunEvent], None]


@dataclass
class ExecutionReport:
    """Final outcome of ``execute_graph``.

    ``completed`` and ``failed`` are lists of PRD ids. ``skipped`` pairs
    each skipped id with a reason (``blocked_by``, ``multi_dep``,
    ``max_runs``, ``not_ready``, …). ``exit_code`` is 0 iff every PRD
    that the executor *attempted* to run succeeded — PRDs that were
    never reached because of ``--max-runs`` or because upstream failures
    pruned their branch do not by themselves cause a non-zero exit, but
    any actual failure does.
    """

    completed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


# ---- Pure traversal helpers -----------------------------------------------


def graph_scope(root_id: str, prds: dict[str, PRD]) -> set[str]:
    """All PRD ids in the execution scope of ``root_id``.

    Scope = {root} ∪ containment descendants of root ∪ transitive unmet
    dependencies reachable from anything already in scope. "Unmet" means
    a dep whose own status is not ``done``; its predecessors are pulled
    in too so ``prd run <leaf-with-unmet-dep>`` walks the dep chain.
    """
    if root_id not in prds:
        return set()

    scope: set[str] = {root_id}
    for d in containment.descendants(root_id, prds):
        scope.add(d.id)

    # Transitive unmet-dependency closure — iterate until fixed point.
    frontier = set(scope)
    while frontier:
        next_frontier: set[str] = set()
        for pid in frontier:
            prd = prds.get(pid)
            if prd is None:
                continue
            for dep_id in prd.depends_on:
                if dep_id not in prds or dep_id in scope:
                    continue
                if prds[dep_id].status == "done":
                    continue
                scope.add(dep_id)
                next_frontier.add(dep_id)
        frontier = next_frontier

    return scope


def actionable_order(scope: set[str], prds: dict[str, PRD]) -> list[str]:
    """Topologically-sorted list of runnable PRD ids within ``scope``.

    Only PRDs that are ``containment.is_runnable`` (leaves or tasks) are
    included — epics and features with children delegate to their
    descendants. Order is determined by a topological sort on the
    ``depends_on`` sub-graph restricted to ``scope``.
    """
    runnable_ids = [pid for pid in scope if containment.is_runnable(prds[pid], prds)]
    runnable_set = set(runnable_ids)

    # Build a restricted graph: edges dep -> dependent, only when both
    # endpoints are in the runnable set.
    sub: dict[str, set[str]] = {pid: set() for pid in runnable_ids}
    for pid in runnable_ids:
        for dep in prds[pid].depends_on:
            if dep in runnable_set:
                sub[dep].add(pid)

    return graph.topological_sort(sub)


def resolve_base_ref(
    prd: PRD,
    completed_this_run: dict[str, str],
    default_base: str,
    prds: dict[str, PRD],
) -> str:
    """Compute the base ref a PRD's worktree should branch from.

    - Exactly one dep completed *this run* → that dep's branch (stacked).
      The completed-this-run map is ``{prd_id: branch_name}``.
    - All deps already ``done`` before this run (no local branches) →
      ``default_base``.
    - No deps at all → ``default_base``.
    - ≥2 deps completed this run → :class:`MultiDepUnsupported`; the
      executor converts this into a skip event pointing at PRD-552.
    - Mix of "done-before-run" and "completed-this-run" with exactly one
      of the latter → stacked on that one.
    """
    if not prd.depends_on:
        return default_base

    # Deps that completed earlier in this invocation — we own their branches.
    stacked_candidates = [d for d in prd.depends_on if d in completed_this_run]
    # Deps that weren't completed this run and also aren't done in the
    # source repo — these are blockers and should never reach resolve_base_ref.
    unmet_external = [
        d
        for d in prd.depends_on
        if d not in completed_this_run and d in prds and prds[d].status != "done"
    ]
    if unmet_external:
        # Shouldn't happen: executor only picks PRDs whose deps are all
        # satisfied. Defensive — treat as multi-dep.
        raise MultiDepUnsupported(prd.id, unmet_external)

    if len(stacked_candidates) == 0:
        return default_base
    if len(stacked_candidates) == 1:
        return completed_this_run[stacked_candidates[0]]
    raise MultiDepUnsupported(prd.id, stacked_candidates)


class MultiDepUnsupported(Exception):
    """Raised when a PRD has ≥2 unmerged deps — blocked on PRD-552."""

    def __init__(self, prd_id: str, unmet: list[str]) -> None:
        self.prd_id = prd_id
        self.unmet = list(unmet)
        super().__init__(
            f"{prd_id} has multiple unmerged dependencies {unmet}; "
            "multi-dep execution requires PRD-552 (merge-upstream task). "
            "Skipping."
        )


# ---- Queue filters and discovery ------------------------------------------


@dataclass
class QueueFilters:
    min_priority: str | None = None
    tags: list[str] = field(default_factory=list)
    exclude_ids: list[str] = field(default_factory=list)


PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def matches_filters(prd: PRD, filters: QueueFilters) -> bool:
    if filters.min_priority:
        threshold = PRIORITY_RANK.get(filters.min_priority, 2)
        if PRIORITY_RANK.get(prd.priority, 2) > threshold:
            return False
    if filters.tags and not any(t in prd.tags for t in filters.tags):
        return False
    if prd.id in filters.exclude_ids:
        return False
    return True


def deps_satisfied(prd: PRD, prds: dict[str, PRD]) -> bool:
    for dep_id in prd.depends_on:
        dep = prds.get(dep_id)
        if dep is None or dep.status not in ("done", "review"):
            return False
    return True


def _prd_sort_key(prd: PRD) -> tuple[int, tuple[int, ...]]:
    from .model import parse_id_sort_key

    return (PRIORITY_RANK.get(prd.priority, 2), parse_id_sort_key(prd.id))


def topo_sort_with_tiebreak(ready: list[PRD], prds: dict[str, PRD]) -> list[PRD]:
    """Topological sort of ``ready`` PRDs with priority-then-number tiebreak.

    Edges in the sub-graph are restricted to those where both endpoints are in
    the ready set. Within a wave of zero-in-degree nodes, higher-priority and
    lower-numbered PRDs come first.
    """
    ready_ids = {p.id for p in ready}
    prd_by_id = {p.id: p for p in ready}

    # Build in-degree and downstream adjacency restricted to the ready set.
    in_degree: dict[str, int] = {p.id: 0 for p in ready}
    downstream: dict[str, list[str]] = {p.id: [] for p in ready}
    for p in ready:
        for dep_id in p.depends_on:
            if dep_id in ready_ids:
                in_degree[p.id] += 1
                downstream[dep_id].append(p.id)

    # Kahn's algorithm with tiebreak.
    wave = sorted(
        [pid for pid, deg in in_degree.items() if deg == 0],
        key=lambda pid: _prd_sort_key(prd_by_id[pid]),
    )
    out: list[PRD] = []

    while wave:
        pid = wave.pop(0)
        out.append(prd_by_id[pid])
        for successor in downstream[pid]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                wave.append(successor)
                wave.sort(key=lambda s: _prd_sort_key(prd_by_id[s]))

    return out


def discover_ready_queue(prds: dict[str, PRD], filters: QueueFilters) -> list[PRD]:
    ready = [
        p
        for p in prds.values()
        if p.status == "ready"
        and deps_satisfied(p, prds)
        and matches_filters(p, filters)
    ]
    return topo_sort_with_tiebreak(ready, prds)


# ---- Candidate strategies -------------------------------------------------


class CandidateStrategy(Protocol):
    """Strategy for selecting which PRD candidates to consider each iteration."""

    def candidates(self, prds: dict[str, PRD]) -> list[str]:
        """Return ordered candidate PRD IDs for this iteration."""
        ...


class RootedStrategy:
    """Candidate strategy for a DAG rooted at a single PRD.

    Reproduces the existing ``graph_scope`` + ``actionable_order`` traversal.
    """

    def __init__(self, root_id: str) -> None:
        self.root_id = root_id

    def candidates(self, prds: dict[str, PRD]) -> list[str]:
        scope = graph_scope(self.root_id, prds)
        return actionable_order(scope, prds)


class QueueStrategy:
    """Candidate strategy that discovers all ready PRDs repo-wide.

    Re-runs ``discover_ready_queue`` on each call so PRDs that become ready
    mid-run (because a dependency just completed) are picked up on the next
    iteration (AC-6).
    """

    def __init__(self, filters: QueueFilters) -> None:
        self.filters = filters

    def candidates(self, prds: dict[str, PRD]) -> list[str]:
        return [p.id for p in discover_ready_queue(prds, self.filters)]


# ---- Dry-run plan ---------------------------------------------------------


@dataclass
class ExecutionSlice:
    """Dry-run view of a graph traversal.

    ``full_dag`` is every PRD at-or-below the root including unmet-dep
    closure, in topological order. ``execution_slice`` is the subset
    that would actually run under the current ``--max-runs``, in order.
    ``skipped`` explains why any scope PRD was omitted (multi-dep,
    not-ready, already-done, …).
    """

    full_dag: list[str]
    execution_slice: list[str]
    skipped: list[tuple[str, str]]


def plan_execution(
    root: PRD | None,
    prds: dict[str, PRD],
    *,
    max_runs: int | None,
    default_base: str,
    strategy: CandidateStrategy | None = None,
) -> ExecutionSlice:
    """Compute the dry-run plan for a root PRD or a candidate strategy.

    ``root`` is the backward-compatible entry point (creates a
    :class:`RootedStrategy` internally). Pass ``strategy`` directly to use
    queue mode or any other custom traversal.
    """
    if strategy is None:
        if root is None:
            raise ValueError("Either strategy or root must be provided")
        strategy = RootedStrategy(root.id)
    order = strategy.candidates(prds)

    skipped: list[tuple[str, str]] = []
    slice_ids: list[str] = []
    completed_this_run: dict[str, str] = {}

    for pid in order:
        prd = prds[pid]
        if prd.status == "done":
            skipped.append((pid, "already done"))
            continue
        if prd.status == "cancelled":
            skipped.append((pid, "cancelled"))
            continue
        if prd.status not in ("ready", "in-progress"):
            skipped.append((pid, f"status={prd.status}"))
            continue
        # Dependency check: all deps must be done or already completed in
        # this simulated run.
        unmet_external = [
            d
            for d in prd.depends_on
            if d in prds and prds[d].status != "done" and d not in completed_this_run
        ]
        if any(
            prds[d].status not in ("ready", "in-progress", "done")
            or d in [x for x, _ in skipped]
            for d in unmet_external
        ):
            skipped.append((pid, "upstream not runnable"))
            continue
        # Multi-dep check.
        unmet = [d for d in prd.depends_on if d in prds and prds[d].status != "done"]
        if len(unmet) >= 2:
            skipped.append((pid, f"multi-dep (see PRD-552): {unmet}"))
            continue
        if max_runs is not None and len(slice_ids) >= max_runs:
            skipped.append((pid, "past --max-runs"))
            continue
        slice_ids.append(pid)
        # Simulate the stacked-branch base for the next iteration.
        completed_this_run[pid] = _compute_branch_name(prd)

    return ExecutionSlice(
        full_dag=order,
        execution_slice=slice_ids,
        skipped=skipped,
    )


# ---- Executor -------------------------------------------------------------


def execute_graph(
    data_dir: Path,
    repo_root: Path,
    workflows: dict[str, Workflow],
    *,
    strategy: CandidateStrategy | None = None,
    root_id: str | None = None,
    default_base: str,
    max_runs: int | None = None,
    model_override: str | None = None,
    workflow_override: str | None = None,
    dry_run: bool = True,
    event_sink: EventSink | None = None,
    run_workflow_fn: Callable[..., RunResult] = run_workflow,
    styler: "Styler | None" = None,
    session_id: str | None = None,
) -> ExecutionReport:
    """Walk the candidate PRDs produced by ``strategy`` and run each in turn.

    Sequential execution. Re-loads PRDs between runs so planning workflows
    can grow the DAG mid-invocation, and so :class:`QueueStrategy` can pick
    up newly-ready PRDs on each iteration. ``run_workflow_fn`` is injectable
    for testing — production code uses the default
    (:func:`runner.run_workflow`).

    Pass ``root_id`` (keyword) for the backward-compatible rooted mode; this
    creates a :class:`RootedStrategy` internally. Pass ``strategy`` to use
    queue mode or any other traversal.
    """
    if strategy is None:
        if root_id is None:
            raise ValueError("Either strategy or root_id must be provided")
        strategy = RootedStrategy(root_id)

    report = ExecutionReport()

    def emit(ev: RunEvent) -> None:
        if event_sink is not None:
            event_sink(ev)

    def _emit_dag_event(target_prd_id: str, event_type: str, **fields: object) -> None:
        """Write a DAG-level event to a per-PRD event file."""
        if session_id and not dry_run:
            try:
                writer = EventWriter(repo_root, session_id, target_prd_id)
                writer.emit("dag", event_type, **fields)
                writer.close()
            except OSError:
                logger.warning("failed to write DAG event for %s", target_prd_id)

    completed_this_run: dict[str, str] = {}
    # Explicit skip list that persists across iterations (e.g. multi-dep
    # errors, failure-pruned dependents). Re-loads don't clear these.
    sticky_skipped: dict[str, str] = {}
    blocked_ids: set[str] = set()

    total_runs = 0

    while True:
        prds = load_all(data_dir)

        # For rooted mode, verify the root still exists after reload.
        if isinstance(strategy, RootedStrategy) and strategy.root_id not in prds:
            report.skipped.append((strategy.root_id, "root PRD not found after reload"))
            break

        order = strategy.candidates(prds)

        # Prune dependents of anything failed/blocked/multi-dep/skipped.
        effective_skipped: set[str] = set(sticky_skipped.keys()) | blocked_ids
        effective_skipped |= _transitive_dependents(effective_skipped, prds)

        picked: PRD | None = None
        for pid in order:
            if pid in effective_skipped:
                continue
            if pid in completed_this_run:
                continue
            prd = prds[pid]
            if prd.status == "done":
                continue
            if prd.status not in ("ready", "in-progress"):
                # Not something we can run. Leave alone.
                continue
            # All deps must be done or completed-this-run.
            deps_ok = True
            for dep_id in prd.depends_on:
                if dep_id not in prds:
                    deps_ok = False
                    break
                if prds[dep_id].status != "done" and dep_id not in completed_this_run:
                    deps_ok = False
                    break
            if not deps_ok:
                continue
            picked = prd
            break

        if picked is None:
            break

        if max_runs is not None and total_runs >= max_runs:
            emit(RunEvent(event="skip", prd_id=picked.id, reason="max_runs"))
            _emit_dag_event(
                picked.id, "prd_skipped", prd_id=picked.id, reason="max_runs"
            )
            report.skipped.append((picked.id, "max_runs"))
            break

        # Multi-dep guard.
        try:
            base_ref = resolve_base_ref(picked, completed_this_run, default_base, prds)
        except MultiDepUnsupported as exc:
            sticky_skipped[picked.id] = f"multi_dep: {exc.unmet}"
            report.skipped.append((picked.id, f"multi_dep: {exc.unmet}"))
            emit(
                RunEvent(
                    event="skip",
                    prd_id=picked.id,
                    reason=f"multi_dep (PRD-552 needed): {exc.unmet}",
                )
            )
            _emit_dag_event(
                picked.id,
                "prd_skipped",
                prd_id=picked.id,
                reason=f"multi_dep (PRD-552 needed): {exc.unmet}",
            )
            continue

        # Resolve workflow for this PRD.
        try:
            if workflow_override and workflow_override in workflows:
                workflow = workflows[workflow_override]
            else:
                workflow = assign.assign_workflow(picked, prds, workflows)
        except KeyError as exc:
            report.failed.append((picked.id, f"workflow assignment failed: {exc}"))
            sticky_skipped[picked.id] = "workflow_assign_failed"
            emit(
                RunEvent(
                    event="skip",
                    prd_id=picked.id,
                    reason=f"workflow_assign_failed: {exc}",
                )
            )
            _emit_dag_event(
                picked.id,
                "prd_skipped",
                prd_id=picked.id,
                reason=f"workflow_assign_failed: {exc}",
            )
            continue

        emit(RunEvent(event="start", prd_id=picked.id, base_ref=base_ref))
        _emit_dag_event(
            picked.id,
            "prd_picked",
            prd_id=picked.id,
            base_ref=base_ref,
            workflow=workflow.name,
        )
        total_runs += 1

        result = run_workflow_fn(
            prd=picked,
            workflow=workflow,
            repo_root=repo_root,
            base_ref=base_ref,
            dry_run=dry_run,
            model_override=model_override,
            styler=styler,
            session_id=session_id,
        )

        if result.success:
            completed_this_run[picked.id] = _compute_branch_name(picked)
            report.completed.append(picked.id)
            emit(
                RunEvent(
                    event="finish",
                    prd_id=picked.id,
                    success=True,
                    pr_url=result.pr_url,
                )
            )
            _emit_dag_event(
                picked.id,
                "prd_finished",
                prd_id=picked.id,
                success=True,
                pr_url=result.pr_url,
            )
        else:
            report.failed.append((picked.id, result.failure_reason or "unknown"))
            blocked_ids.add(picked.id)
            # Mark the source PRD file as blocked so downstream invocations
            # can see it. Best-effort — set_status mutation failures must
            # not crash the executor.
            if not dry_run:
                try:
                    set_status_at(picked.path, "blocked")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("failed to mark %s blocked: %s", picked.id, exc)
            emit(
                RunEvent(
                    event="finish",
                    prd_id=picked.id,
                    success=False,
                    failure_reason=result.failure_reason,
                )
            )
            _emit_dag_event(
                picked.id,
                "prd_finished",
                prd_id=picked.id,
                success=False,
                failure_reason=result.failure_reason,
            )
            _emit_dag_event(
                picked.id,
                "prd_blocked",
                prd_id=picked.id,
                reason=result.failure_reason or "unknown",
            )

    return report


def _transitive_dependents(seed_ids: set[str], prds: dict[str, PRD]) -> set[str]:
    """All PRDs that transitively depend on any id in ``seed_ids``."""
    if not seed_ids:
        return set()
    g = graph.build_graph(prds)
    out: set[str] = set()
    frontier = set(seed_ids)
    while frontier:
        next_frontier: set[str] = set()
        for pid in frontier:
            for dep_of in g.get(pid, ()):
                if dep_of not in out and dep_of not in seed_ids:
                    out.add(dep_of)
                    next_frontier.add(dep_of)
        frontier = next_frontier
    return out
