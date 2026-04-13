"""CLI ``prd run`` subcommand and supporting helpers."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from darkfactory.config import load_section
from darkfactory.event_log import generate_session_id
from darkfactory.graph import (
    QueueFilters,
    QueueStrategy,
    RunEvent,
    assign,
    containment,
    deps_satisfied,
    execute_graph,
    plan_execution,
)
from darkfactory.model import PRD
from darkfactory.runner import run_workflow
from darkfactory.style import Element, Styler
from darkfactory.workflow import Workflow

from darkfactory.cli._shared import (
    _check_runnable,
    _find_repo_root,
    _load,
    _load_workflows_or_fail,
    _resolve_base_ref,
    _resolve_prd_or_exit,
)


def _read_config_timeouts(repo_root: Path) -> dict[str, object] | None:
    """Return the ``[timeouts]`` section from ``.darkfactory/config.toml``, or None."""
    config_path = repo_root / ".darkfactory" / "config.toml"
    if not config_path.exists():
        return None
    try:
        result = load_section(config_path, "timeouts")
        return result if result else None
    except Exception:  # noqa: BLE001
        return None


def _is_graph_target(prd: PRD, prds: Mapping[str, PRD]) -> bool:
    """True if ``prd run`` should walk the DAG rather than run a single PRD.

    Routes through the graph executor when the target has children (epic
    or feature with decomposition) or any unfinished ``depends_on`` —
    both cases require multi-PRD orchestration. A plain ready leaf with
    all deps satisfied goes through the legacy single-PRD path.
    """
    if not containment.is_leaf(prd, prds):
        return True
    for dep_id in prd.depends_on:
        dep = prds.get(dep_id)
        if dep is None:
            continue
        if dep.status != "done":
            return True
    return False


def cmd_run(args: argparse.Namespace) -> int:
    """Run a workflow against a PRD. Defaults to dry-run; opt in via --execute.

    - **Queue mode (--all):** runs all ready PRDs repo-wide, filtered by
      ``--priority``, ``--tag``, and ``--exclude``.
    - **Single leaf with deps satisfied:** legacy path — one worktree,
      one workflow run.
    - **Epic/feature with children, or leaf with unmet deps:** graph
      execution — walks the DAG in topological order, running each
      actionable leaf in its own worktree. Sequential only (PRD-220).
      Parallel fan-out is PRD-551.
    """
    run_all = getattr(args, "run_all", False)
    prd_id = getattr(args, "prd_id", None)

    if run_all and prd_id:
        print("error: --all and PRD ID are mutually exclusive", file=sys.stderr)
        return 1
    if not run_all and not prd_id:
        print("error: provide either a PRD ID or --all", file=sys.stderr)
        return 1

    prds = _load(args.data_dir)
    workflows = _load_workflows_or_fail(args.workflows_dir)
    repo_root = _find_repo_root(args.data_dir)
    base_ref = _resolve_base_ref(args.base, repo_root)
    dry_run = not args.execute
    styler: Styler = args.styler

    if run_all:
        filters = QueueFilters(
            min_priority=getattr(args, "priority", None),
            tags=getattr(args, "tags", None) or [],
            exclude_ids=getattr(args, "exclude_ids", None) or [],
        )
        strategy = QueueStrategy(filters)
        return _cmd_run_queue(
            args=args,
            strategy=strategy,
            prds=prds,
            workflows=workflows,
            repo_root=repo_root,
            default_base=base_ref,
            dry_run=dry_run,
            styler=styler,
        )

    assert prd_id is not None  # guarded by the not-prd_id check above
    prd = _resolve_prd_or_exit(prd_id, prds)

    if _is_graph_target(prd, prds):
        return _cmd_run_graph(
            args=args,
            prd=prd,
            prds=prds,
            workflows=workflows,
            repo_root=repo_root,
            default_base=base_ref,
            dry_run=dry_run,
            styler=styler,
        )

    # Legacy single-PRD path.
    if args.workflow:
        if args.workflow not in workflows:
            raise SystemExit(f"unknown workflow: {args.workflow}")
        workflow = workflows[args.workflow]
    else:
        try:
            workflow = assign.assign_workflow(prd, prds, workflows)
        except KeyError as exc:
            raise SystemExit(str(exc))

    if args.execute:
        err = _check_runnable(prd, prds)
        if err:
            raise SystemExit(f"cannot run: {err}")

    header_label = "Dry-run" if dry_run else "Executing"
    print(
        styler.render(
            Element.RUN_HEADER,
            f"# {header_label}: {prd.id} via workflow {workflow.name!r}",
        )
    )

    config_timeouts = _read_config_timeouts(repo_root)
    session = generate_session_id() if not dry_run else None

    result = run_workflow(
        prd=prd,
        workflow=workflow,
        repo_root=repo_root,
        base_ref=base_ref,
        dry_run=dry_run,
        model_override=args.model,
        cli_timeout_minutes=getattr(args, "timeout", None),
        config_timeouts=config_timeouts,
        styler=styler,
        session_id=session,
    )

    print()
    print("  Steps:")
    for step in result.steps:
        step_elem = Element.RUN_SUCCESS if step.success else Element.RUN_FAILURE
        marker = "✓" if step.success else "✗"
        detail = f" — {step.detail}" if step.detail else ""
        print(
            f"    {styler.render(step_elem, marker)} [{step.kind}] {step.name}{detail}"
        )

    print()
    if result.success:
        print(f"  Result: {styler.render(Element.RUN_SUCCESS, '✓ success')}")
        if result.pr_url:
            print(f"  PR:     {result.pr_url}")
        return 0
    else:
        print(
            f"  Result: {styler.render(Element.RUN_FAILURE, '✗ FAILED')} — {result.failure_reason}"
        )
        return 1


def _cmd_run_queue(
    *,
    args: argparse.Namespace,
    strategy: QueueStrategy,
    prds: dict[str, PRD],
    workflows: dict[str, Workflow],
    repo_root: Path,
    default_base: str,
    dry_run: bool,
    styler: Styler,
) -> int:
    """Queue-execution path for ``prd run --all``.

    In dry-run (the default), prints the ordered ready queue with each PRD's
    ID, title, priority, and dependency status. With ``--execute``, actually
    runs all queued PRDs sequentially via :func:`graph_execution.execute_graph`.
    """
    max_runs: int | None = args.max_runs

    if dry_run:
        plan = plan_execution(
            None,
            prds,
            max_runs=max_runs,
            default_base=default_base,
            strategy=strategy,
        )

        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "queue",
                        "default_base": default_base,
                        "execution_slice": plan.execution_slice,
                        "skipped": [
                            {"prd_id": pid, "reason": reason}
                            for pid, reason in plan.skipped
                        ],
                        "max_runs": max_runs,
                    },
                    indent=2,
                )
            )
            return 0

        print(
            styler.render(
                Element.RUN_HEADER,
                "# Dry-run queue (--all)",
            )
        )
        print()

        if not plan.execution_slice:
            print("  (no ready PRDs match the current filters)")
            return 0

        print(f"  Ready queue ({len(plan.execution_slice)} PRDs will run):")
        for i, pid in enumerate(plan.execution_slice, start=1):
            prd = prds.get(pid)
            title = prd.title if prd else "?"
            priority = prd.priority if prd else "?"
            dep_note = (
                ("deps satisfied" if deps_satisfied(prd, prds) else "deps pending")
                if prd
                else "?"
            )
            print(f"    {i:>2}. {pid} [{priority}] {title!r} — {dep_note}")

        if plan.skipped:
            print()
            print("  Skipped:")
            for pid, reason in plan.skipped:
                print(f"    - {pid}: {reason}")
        return 0

    # --execute path.
    print(
        styler.render(
            Element.RUN_HEADER,
            "# Executing queue (--all)",
        )
    )
    return _execute_graph_with_reporting(
        args=args,
        repo_root=repo_root,
        workflows=workflows,
        default_base=default_base,
        max_runs=max_runs,
        styler=styler,
        strategy=strategy,
    )


def _cmd_run_graph(
    *,
    args: argparse.Namespace,
    prd: PRD,
    prds: dict[str, PRD],
    workflows: dict[str, Workflow],
    repo_root: Path,
    default_base: str,
    dry_run: bool,
    styler: Styler,
) -> int:
    """Graph-execution path for ``prd run``.

    In dry-run (the default), prints the full DAG + the execution slice
    that would run under ``--max-runs``. With ``--execute``, actually
    walks the DAG via :func:`graph_execution.execute_graph`, streaming
    events and returning a non-zero exit on any failure.
    """
    max_runs: int | None = args.max_runs

    if dry_run:
        plan = plan_execution(
            prd,
            prds,
            max_runs=max_runs,
            default_base=default_base,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "root": prd.id,
                        "default_base": default_base,
                        "full_dag": plan.full_dag,
                        "execution_slice": plan.execution_slice,
                        "skipped": [
                            {"prd_id": pid, "reason": reason}
                            for pid, reason in plan.skipped
                        ],
                        "max_runs": max_runs,
                    },
                    indent=2,
                )
            )
            return 0

        print(
            styler.render(
                Element.RUN_HEADER,
                f"# Dry-run graph: {prd.id} (base {default_base})",
            )
        )
        print()
        print(f"  Full DAG ({len(plan.full_dag)} runnable PRDs):")
        for i, pid in enumerate(plan.full_dag, start=1):
            status = prds[pid].status if pid in prds else "?"
            print(f"    {i:>2}. {pid} [{status}]")
        print()
        print(f"  Execution slice ({len(plan.execution_slice)} PRDs will run):")
        if not plan.execution_slice:
            print("    (nothing to run)")
        for i, pid in enumerate(plan.execution_slice, start=1):
            print(f"    {i:>2}. {pid}")
        if plan.skipped:
            print()
            print("  Skipped:")
            for pid, reason in plan.skipped:
                print(f"    - {pid}: {reason}")
        return 0

    # --execute path.
    print(
        styler.render(
            Element.RUN_HEADER,
            f"# Executing graph: {prd.id} (base {default_base})",
        )
    )
    return _execute_graph_with_reporting(
        args=args,
        repo_root=repo_root,
        workflows=workflows,
        default_base=default_base,
        max_runs=max_runs,
        styler=styler,
        root_id=prd.id,
    )


def _execute_graph_with_reporting(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    workflows: dict[str, Workflow],
    default_base: str,
    max_runs: int | None,
    styler: Styler,
    root_id: str | None = None,
    strategy: QueueStrategy | None = None,
) -> int:
    """Execute graph mode and print streamed events plus final summary."""

    def sink(ev: RunEvent) -> None:
        if args.json:
            print(json.dumps(ev.as_dict()), flush=True)
        else:
            _print_run_event(ev, styler)

    session = generate_session_id()
    report = execute_graph(
        root_id=root_id,
        data_dir=args.data_dir,
        repo_root=repo_root,
        workflows=workflows,
        strategy=strategy,
        default_base=default_base,
        max_runs=max_runs,
        model_override=args.model,
        workflow_override=args.workflow,
        dry_run=False,
        event_sink=sink,
        styler=styler,
        session_id=session,
    )

    print()
    print(f"  Completed: {len(report.completed)}")
    for pid in report.completed:
        print(f"    {styler.render(Element.RUN_SUCCESS, '✓')} {pid}")
    if report.failed:
        print(f"  Failed: {len(report.failed)}")
        for pid, reason in report.failed:
            print(f"    {styler.render(Element.RUN_FAILURE, '✗')} {pid} — {reason}")
    if report.skipped:
        print(f"  Skipped: {len(report.skipped)}")
        for pid, reason in report.skipped:
            print(f"    - {pid}: {reason}")
    return report.exit_code


def _print_run_event(ev: RunEvent, styler: Styler) -> None:
    if ev.event == "start":
        base = f" (base {ev.base_ref})" if ev.base_ref else ""
        print(f"  → start {ev.prd_id}{base}")
    elif ev.event == "finish":
        if ev.success:
            marker = styler.render(Element.RUN_SUCCESS, "✓")
            pr = f" {ev.pr_url}" if ev.pr_url else ""
            print(f"  {marker} finish {ev.prd_id}{pr}")
        else:
            marker = styler.render(Element.RUN_FAILURE, "✗")
            print(f"  {marker} finish {ev.prd_id} — {ev.failure_reason or 'failed'}")
    elif ev.event == "skip":
        print(f"  ↷ skip {ev.prd_id}: {ev.reason}")
