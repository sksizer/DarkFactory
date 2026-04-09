"""CLI package — re-export hub.

Holds cmd_* functions temporarily until extracted by subsequent PRDs.
Re-exports main and build_parser for backwards compatibility.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from darkfactory import assign, checks, containment, graph, impacts
from darkfactory.event_log import generate_session_id
from darkfactory.graph_execution import (
    QueueFilters,
    QueueStrategy,
    RunEvent,
    deps_satisfied,
    execute_graph,
    plan_execution,
)
from darkfactory.invoke import capability_to_model
from darkfactory.prd import (
    PRD,
    PRD_ID_RE,
    dump_frontmatter,
    load_all,
    normalize_list_field_at,
    parse_id_sort_key,
    set_workflow,
    update_frontmatter_field_at,
)
from darkfactory.runner import _compute_branch_name, _pick_model, run_workflow
from darkfactory.style import Element, Styler
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Task, Workflow

from darkfactory.init import init_project

from darkfactory.cli._shared import (
    PRIORITY_ORDER,  # noqa: F401
    EFFORT_ORDER,  # noqa: F401
    CAPABILITY_ORDER,  # noqa: F401
    _find_repo_root,
    _load_workflows_or_fail,
    _action_sort_key,  # noqa: F401
    _load,
)
from darkfactory.cli._parser import build_parser
from darkfactory.cli.main import main
from darkfactory.cli.cleanup import cmd_cleanup  # noqa: F401
from darkfactory.cli.children import cmd_children  # noqa: F401
from darkfactory.cli.new import cmd_new, _slugify, _next_flat_prd_id  # noqa: F401
from darkfactory.cli.next_cmd import cmd_next  # noqa: F401
from darkfactory.cli.status import cmd_status  # noqa: F401

__all__ = ["main", "build_parser", "cmd_cleanup", "cmd_children", "cmd_new", "cmd_next", "cmd_status", "_slugify", "_next_flat_prd_id"]


def _read_config_timeouts(repo_root: Path) -> dict[str, object] | None:
    """Return the ``[timeouts]`` section from ``.darkfactory/config.toml``, or None."""
    config_path = repo_root / ".darkfactory" / "config.toml"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        section = data.get("timeouts")
        return section if isinstance(section, dict) else None
    except Exception:  # noqa: BLE001
        return None


def cmd_init(args: argparse.Namespace) -> int:
    target = (args.directory or Path.cwd()).resolve()
    try:
        msg = init_project(target)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(msg)
    return 0


    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Filename ↔ id consistency
    for prd in prds.values():
        if not prd.path.name.startswith(f"{prd.id}-"):
            errors.append(f"{prd.path.name}: id {prd.id!r} does not match filename")

    # 2. Missing dep references
    for prd in prds.values():
        for dep_id in prd.depends_on:
            if dep_id not in prds:
                errors.append(f"{prd.id}: depends_on references unknown {dep_id}")
        for blk_id in prd.blocks:
            if blk_id not in prds:
                errors.append(f"{prd.id}: blocks references unknown {blk_id}")
        if prd.parent and prd.parent not in prds:
            errors.append(f"{prd.id}: parent references unknown {prd.parent}")

    # 3. Cycles in dependency DAG
    g = graph.build_graph(prds)
    cycles = graph.detect_cycles(g)
    for cycle in cycles:
        errors.append(f"dependency cycle: {' -> '.join(cycle)} -> {cycle[0]}")

    # 4. Containment tree cycles
    for prd in prds.values():
        seen = {prd.id}
        cur = prd
        while cur.parent:
            if cur.parent in seen:
                errors.append(f"{prd.id}: containment cycle via parent chain")
                break
            seen.add(cur.parent)
            nxt = prds.get(cur.parent)
            if nxt is None:
                break
            cur = nxt

    # 5. Container PRDs must have empty impacts.
    # The leaf-only rule (see impacts.py) gives us a single source of
    # truth: containers' effective impacts are computed from their
    # descendants, so declared impacts on a container would be a
    # divergent second source that could silently drift.
    for prd in prds.values():
        kids = containment.children(prd.id, prds)
        if kids and prd.impacts:
            errors.append(
                f"{prd.id}: container PRD (has {len(kids)} children) "
                f"must have impacts: [] — declared impacts on containers "
                f"create divergence with the computed descendant union "
                f"(got {prd.impacts!r})"
            )

    # 6. Impact overlap warnings (ready PRDs only).
    # Uses effective_impacts (aggregated for containers) and exempts
    # parent/child pairs (containment is not conflict).
    try:
        repo_root = _find_repo_root(args.prd_dir)
        files = impacts.tracked_files(repo_root)
    except Exception:  # noqa: BLE001 — best-effort outside a git repo
        files = []

    if files:
        ready = [p for p in prds.values() if p.status == "ready"]
        for i, a in enumerate(ready):
            for b in ready[i + 1 :]:
                # Skip if there's an explicit dep relation in either direction.
                if b.id in a.depends_on or a.id in b.depends_on:
                    continue
                try:
                    overlap = impacts.impacts_overlap(a, b, files, prds)
                except ValueError:
                    # effective_impacts refused — already reported by the
                    # container-has-impacts check above. Skip silently
                    # here so we don't double-report.
                    continue
                if overlap:
                    warnings.append(
                        f"{a.id} and {b.id} have overlapping impacts "
                        f"({len(overlap)} files) but no explicit dependency"
                    )

    # 7. Undeclared impacts on leaves (informational)
    undeclared = [
        p.id
        for p in prds.values()
        if p.status == "ready"
        and not p.impacts
        and not containment.children(p.id, prds)  # leaves only
    ]
    if undeclared and args.verbose:
        warnings.append(
            f"{len(undeclared)} ready leaf PRDs have no declared impacts "
            "(undeclared = sequential)"
        )

    # 8. Review-status PRDs whose branch is gone from origin.
    try:
        repo_root = _find_repo_root(args.prd_dir)
        git_state = checks.SubprocessGitState(str(repo_root))
        for issue in checks.validate_review_branches(prds, git_state):
            warnings.append(issue.message)
    except Exception:  # noqa: BLE001 — best-effort outside a git repo
        pass

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    for warn in warnings:
        print(f"WARN:  {warn}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(prds)} PRDs valid ({len(warnings)} warning(s))")
    return 0


def _format_tree_node(prd: PRD, styler: Styler) -> str:
    """Return a styled inline descriptor for a tree node: ``[kind/status]  title``."""
    kind_elem = styler.kind_element(prd.kind)
    kind_icon = styler.icon(prd.kind)
    status_icon = styler.icon(prd.status)
    priority_icon = styler.icon(prd.priority)

    styled_id = styler.render(kind_elem, prd.id)
    styled_kind = styler.render(kind_elem, f"{kind_icon}{prd.kind}")
    styled_status = styler.render(Element.TREE_STATUS, f"{status_icon}{prd.status}")
    styled_priority = styler.render(
        Element.TREE_PRIORITY, f"{priority_icon}{prd.priority}"
    )
    return (
        f"{styled_id}  [{styled_kind}/{styled_status}/{styled_priority}]  {prd.title}"
    )


def _print_tree(
    prd: PRD,
    prds: dict[str, PRD],
    styler: Styler,
    prefix: str = "",
    is_last: bool = True,
) -> None:
    """Recursively print a containment tree branch."""
    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{_format_tree_node(prd, styler)}")
    extension = "    " if is_last else "│   "
    kids = containment.children(prd.id, prds)
    for i, kid in enumerate(kids):
        _print_tree(kid, prds, styler, prefix + extension, i == len(kids) - 1)


def cmd_tree(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    styler: Styler = args.styler
    if args.prd_id:
        prd = prds.get(args.prd_id)
        if prd is None:
            raise SystemExit(f"unknown PRD id: {args.prd_id}")
        print(_format_tree_node(prd, styler))
        kids = containment.children(prd.id, prds)
        for i, kid in enumerate(kids):
            _print_tree(kid, prds, styler, "", i == len(kids) - 1)
    else:
        for root in containment.roots(prds):
            print(_format_tree_node(root, styler))
            kids = containment.children(root.id, prds)
            for i, kid in enumerate(kids):
                _print_tree(kid, prds, styler, "", i == len(kids) - 1)
            print()
    return 0


def cmd_orphans(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    rs = containment.roots(prds)
    for prd in rs:
        print(f"{prd.id:14} [{prd.kind}/{prd.status}]  {prd.title}")
    return 0


def cmd_undecomposed(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    candidates = [
        prd
        for prd in prds.values()
        if prd.kind in ("epic", "feature")
        and prd.status == "ready"
        and not containment.is_fully_decomposed(prd, prds)
    ]
    candidates.sort(key=lambda p: parse_id_sort_key(p.id))
    if not candidates:
        print("(no undecomposed epics/features)")
        return 0
    for prd in candidates:
        print(f"{prd.id:14} [{prd.kind}]  {prd.title}")
    return 0


def cmd_conflicts(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    prd = prds[args.prd_id]
    repo_root = _find_repo_root(args.prd_dir)
    conflicts = impacts.find_conflicts(prd, prds, repo_root)

    # Use effective_impacts so containers show their aggregated view
    # (union of descendants) rather than an empty declared list.
    try:
        effective = impacts.effective_impacts(prd, prds)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.json:
        print(
            json.dumps(
                {
                    "id": prd.id,
                    "effective_impacts": effective,
                    "conflicts": [
                        {"id": other_id, "files": sorted(files)}
                        for other_id, files in conflicts
                    ],
                },
                indent=2,
            )
        )
        return 0

    if not effective:
        kids = containment.children(prd.id, prds)
        if kids:
            print(
                f"{prd.id} is a container with {len(kids)} children that "
                "have no declared impacts yet"
            )
        else:
            print(f"{prd.id} has no declared impacts; cannot compute overlaps")
        return 0
    if not conflicts:
        print(f"{prd.id} has no impact conflicts with other PRDs")
        print(f"  (effective impact set: {len(effective)} pattern(s))")
        return 0

    print(f"{prd.id} conflicts:")
    for other_id, files in conflicts:
        print(f"  {other_id}:")
        for f in sorted(files):
            print(f"    {f}")
    return 0


def cmd_list_workflows(args: argparse.Namespace) -> int:
    """List all loaded workflows with priority and description."""
    workflows = _load_workflows_or_fail(args.workflows_dir)
    if not workflows:
        print("(no workflows loaded)")
        return 0

    # Sort by descending priority then alphabetically for stable display.
    sorted_wfs = sorted(
        workflows.values(),
        key=lambda w: (-w.priority, w.name),
    )

    if args.json:
        payload = [
            {
                "name": w.name,
                "priority": w.priority,
                "description": w.description,
                "task_count": len(w.tasks),
                "workflow_dir": str(w.workflow_dir) if w.workflow_dir else None,
            }
            for w in sorted_wfs
        ]
        print(json.dumps(payload, indent=2))
        return 0

    for w in sorted_wfs:
        # Header line: name, priority, task count
        print(f"{w.name:20} priority={w.priority:<3} tasks={len(w.tasks)}")
        if w.description:
            # Indent description under the header
            for line in w.description.splitlines():
                print(f"  {line}")
        print()
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    """Compute the workflow assignment for every PRD, optionally persist.

    Output is a table of ``PRD-id -> workflow-name``. With ``--write``,
    the resolved workflow name is persisted into each PRD's frontmatter
    (only for PRDs that don't already have an explicit workflow field —
    the command is idempotent on re-run).
    """
    prds = _load(args.prd_dir)
    workflows = _load_workflows_or_fail(args.workflows_dir)

    if not workflows:
        if args.json:
            print(json.dumps([], indent=2))
        else:
            print(f"{'PRD':14} {'Workflow':20} Source")
            print("-" * 50)
        return 0

    try:
        assignments = assign.assign_all(prds, workflows)
    except KeyError as exc:
        raise SystemExit(str(exc))

    if args.json:
        payload = [
            {
                "id": prd_id,
                "workflow": wf.name,
                "explicit": prds[prd_id].workflow is not None,
            }
            for prd_id, wf in sorted(
                assignments.items(),
                key=lambda kv: parse_id_sort_key(kv[0]),
            )
        ]
        print(json.dumps(payload, indent=2))
        return 0

    # Human-readable table. Mark explicit assignments with a `*`.
    print(f"{'PRD':14} {'Workflow':20} Source")
    print("-" * 50)
    for prd_id in sorted(assignments.keys(), key=parse_id_sort_key):
        wf = assignments[prd_id]
        source = "explicit" if prds[prd_id].workflow else "predicate"
        print(f"{prd_id:14} {wf.name:20} {source}")

    if args.write:
        written = 0
        for prd_id, wf in assignments.items():
            prd = prds[prd_id]
            if prd.workflow is None:
                set_workflow(prd, wf.name)
                written += 1
        print(f"\nPersisted {written} workflow assignments to frontmatter.")
    return 0


#: List fields that ``prd normalize`` canonicalizes.
_NORMALIZABLE_FIELDS: tuple[str, ...] = ("tags", "impacts", "depends_on", "blocks")


def _normalize_prd(prd: PRD, check_only: bool) -> bool:
    """Normalize all list fields of a single PRD. Returns True if changed."""
    changed = False
    for field in _NORMALIZABLE_FIELDS:
        raw = prd.raw_frontmatter.get(field)
        if raw is None:
            continue
        if not isinstance(raw, list):
            continue
        items = [str(v) for v in raw]
        try:
            if normalize_list_field_at(prd.path, field, items, write=not check_only):
                changed = True
        except ValueError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)
    return changed


def cmd_normalize(args: argparse.Namespace) -> int:
    """Canonicalize list fields in one or all PRD files.

    Sorts ``tags``, ``impacts``, ``depends_on``, and ``blocks`` into their
    canonical order (alphabetical for tags/impacts, natural PRD-ID order for
    the dependency fields) and rewrites only the affected lines on disk.

    With ``--check``, prints how many files would change and exits non-zero
    without writing anything — suitable for CI.
    """
    prds = _load(args.prd_dir)

    if args.all:
        targets = sorted(prds.values(), key=lambda p: parse_id_sort_key(p.id))
    elif args.prd_id:
        if args.prd_id not in prds:
            raise SystemExit(f"unknown PRD id: {args.prd_id}")
        targets = [prds[args.prd_id]]
    else:
        raise SystemExit("specify a PRD id or --all")

    changed_count = 0
    for prd in targets:
        if _normalize_prd(prd, check_only=args.check):
            changed_count += 1
            if not args.check:
                print(f"normalized: {prd.id}")

    if args.check:
        if changed_count:
            print(
                f"{changed_count} file(s) would be changed",
                file=sys.stderr,
            )
            return 1
        print(f"OK: all {len(targets)} file(s) already canonical")
        return 0

    if changed_count:
        print(f"Normalized {changed_count} of {len(targets)} file(s).")
    else:
        print(f"No changes — {len(targets)} file(s) already canonical.")
    return 0


def _describe_task(task: Task, ctx_prd: PRD, model_override: str | None) -> str:
    """Produce a one-line human-readable description of a task for `prd plan`."""
    if isinstance(task, BuiltIn):
        kwargs_str = (
            " " + ", ".join(f"{k}={v!r}" for k, v in task.kwargs.items())
            if task.kwargs
            else ""
        )
        return f"builtin: {task.name}{kwargs_str}"
    if isinstance(task, AgentTask):
        model = _pick_model(task, ctx_prd, override=model_override)
        prompts = ", ".join(task.prompts) or "(none)"
        tools_count = len(task.tools)
        return (
            f"agent: {task.name} [model={model}, prompts={prompts}, "
            f"tools={tools_count}, retries={task.retries}]"
        )
    if isinstance(task, ShellTask):
        return f"shell: {task.name} ({task.on_failure}) -> {task.cmd}"
    return f"unknown task type: {type(task).__name__}"


def _resolve_base_ref(explicit: str | None, repo_root: Path) -> str:
    """Determine the git base ref for a new workflow branch.

    Resolution order:

    1. ``explicit`` from ``--base`` (highest priority)
    2. ``DARKFACTORY_BASE_REF`` environment variable
    3. ``main`` if it exists locally
    4. ``master`` if it exists locally
    5. The remote's default branch via ``origin/HEAD``
    6. Last resort: ``main`` (callers will hit a real error later if it's
       missing too)

    The user's current branch is **not** consulted. PRDs are independent
    units of work and should base on the project's default branch unless
    the user says otherwise. Stacking onto a feature branch is the
    exception, not the rule, and requires an explicit ``--base`` flag.
    """
    if explicit:
        return explicit

    env_override = os.environ.get("DARKFACTORY_BASE_REF")
    if env_override:
        return env_override

    for candidate in ("main", "master"):
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-parse",
                "--verify",
                "--quiet",
                f"refs/heads/{candidate}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return candidate

    # Try remote's default branch (e.g. for fresh clones with no local main)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        # Output looks like "refs/remotes/origin/main"
        return result.stdout.strip().rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass

    return "main"


def _check_runnable(prd: PRD, prds: dict[str, PRD]) -> str | None:
    """Return an error string if the PRD can't be run, else None."""
    if prd.status == "done":
        return f"{prd.id} is already done"
    if prd.status == "cancelled":
        return f"{prd.id} is cancelled"
    if not graph.is_actionable(prd, prds):
        missing = graph.missing_deps(prd, prds)
        if missing:
            return f"{prd.id} depends on missing PRDs: {', '.join(missing)}"
        unfinished = [
            dep_id
            for dep_id in prd.depends_on
            if dep_id in prds and prds[dep_id].status != "done"
        ]
        if unfinished:
            return f"{prd.id} has unfinished dependencies: " + ", ".join(
                f"{d} ({prds[d].status})" for d in unfinished
            )
        return f"{prd.id} status is {prd.status!r}, not 'ready'"
    if not containment.is_runnable(prd, prds):
        return (
            f"{prd.id} is an epic/feature with children; "
            "use the planning workflow or run its task descendants instead"
        )
    return None


def cmd_plan(args: argparse.Namespace) -> int:
    """Show the execution plan for a PRD without touching anything.

    Resolves the workflow, computes the branch name + base ref + model,
    and prints the ordered task list with descriptions. No git
    operations, no subprocess, no agent invocation.
    """
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    prd = prds[args.prd_id]

    workflows = _load_workflows_or_fail(args.workflows_dir)

    # Resolve workflow (respecting --workflow override).
    if args.workflow:
        if args.workflow not in workflows:
            raise SystemExit(f"unknown workflow: {args.workflow}")
        workflow = workflows[args.workflow]
    else:
        try:
            workflow = assign.assign_workflow(prd, prds, workflows)
        except KeyError as exc:
            raise SystemExit(str(exc))

    branch = _compute_branch_name(prd)
    repo_root = _find_repo_root(args.prd_dir)
    base_ref = _resolve_base_ref(args.base, repo_root)

    # Note any runnability issues as warnings (plan still shows, but
    # the user gets a heads-up that `prd run --execute` would refuse).
    runnable_error = _check_runnable(prd, prds)

    if args.json:
        payload: dict[str, object] = {
            "prd": {
                "id": prd.id,
                "title": prd.title,
                "kind": prd.kind,
                "status": prd.status,
                "capability": prd.capability,
            },
            "workflow": {
                "name": workflow.name,
                "description": workflow.description,
                "priority": workflow.priority,
            },
            "branch": branch,
            "base_ref": base_ref,
            "default_model": capability_to_model(prd.capability),
            "tasks": [_describe_task(task, prd, args.model) for task in workflow.tasks],
            "runnable_error": runnable_error,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"# Plan for {prd.id}: {prd.title}")
    print()
    print(f"  kind:       {prd.kind}")
    print(f"  status:     {prd.status}")
    print(
        f"  capability: {prd.capability} -> default model {capability_to_model(prd.capability)}"
    )
    print()
    tmpl_tag = (
        f"template: {workflow.template_name}"
        if workflow.template_name
        else "no template"
    )
    print(f"  workflow:   {workflow.name} ({tmpl_tag})")
    if workflow.description:
        print(f"  — {workflow.description}")
    print()
    print(f"  branch:     {branch}")
    print(f"  base ref:   {base_ref}")
    print()
    print(f"  tasks ({len(workflow.tasks)}):")
    for i, task in enumerate(workflow.tasks, start=1):
        print(f"    {i:>2}. {_describe_task(task, prd, args.model)}")

    if runnable_error:
        print()
        print(f"  ⚠ NOT RUNNABLE: {runnable_error}")
        print("    (`prd run --execute` would refuse this PRD)")
    return 0


def _is_graph_target(prd: PRD, prds: dict[str, PRD]) -> bool:
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

    prds = _load(args.prd_dir)
    workflows = _load_workflows_or_fail(args.workflows_dir)
    repo_root = _find_repo_root(args.prd_dir)
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

    if prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {prd_id}")
    prd = prds[prd_id]

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

    events: list[RunEvent] = []

    def sink(ev: RunEvent) -> None:
        events.append(ev)
        if args.json:
            print(json.dumps(ev.as_dict()), flush=True)
        else:
            _print_run_event(ev, styler)

    session = generate_session_id()

    report = execute_graph(
        prd_dir=args.prd_dir,
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

    events: list[RunEvent] = []

    def sink(ev: RunEvent) -> None:
        events.append(ev)
        if args.json:
            print(json.dumps(ev.as_dict()), flush=True)
        else:
            _print_run_event(ev, styler)

    session = generate_session_id()

    report = execute_graph(
        root_id=prd.id,
        prd_dir=args.prd_dir,
        repo_root=repo_root,
        workflows=workflows,
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


def find_worktree(prd_id: str, repo_root: Path) -> Path | None:
    """Find the worktree path for the given PRD id using git worktree list.

    Returns the worktree path if found, or None if no worktree exists.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return None
    except FileNotFoundError:
        return None

    current_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :]
        elif line.startswith("branch "):
            branch_ref = line[len("branch ") :]
            # branch refs/heads/prd/PRD-NNN-slug
            branch = branch_ref.removeprefix("refs/heads/")
            if re.match(rf"^prd/{re.escape(prd_id)}-", branch):
                return Path(current_path) if current_path else None
    return None


def find_open_pr(branch_name: str, repo_root: Path) -> int | None:
    """Find the PR number for an open PR on the given branch.

    Returns the PR number if an open PR exists, or None otherwise.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch_name,
                "--state",
                "open",
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return None
        prs: list[dict[str, Any]] = json.loads(result.stdout)
        if prs:
            return int(prs[0]["number"])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        pass
    return None


def cmd_rework(args: argparse.Namespace) -> int:
    """Rework a PRD by addressing PR review feedback. Defaults to dry-run; opt in via --execute."""
    prds = _load(args.prd_dir)
    prd_id = args.prd_id
    if prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {prd_id}")
    prd = prds[prd_id]

    if prd.status != "review":
        raise SystemExit(f"ERROR: {prd_id} is in '{prd.status}', not 'review'")

    repo_root = _find_repo_root(args.prd_dir)

    worktree_path = find_worktree(prd_id, repo_root)
    if worktree_path is None:
        raise SystemExit(
            f"ERROR: No worktree found for {prd_id}. Run 'prd run {prd_id}' first."
        )

    branch_name = _compute_branch_name(prd)
    pr_number = find_open_pr(branch_name, repo_root)
    if pr_number is None:
        raise SystemExit(f"ERROR: No open PR found for {prd_id}")

    if not args.execute:
        print(f"Would rework {prd_id}")
        print(f"  Worktree: {worktree_path}")
        print(f"  PR: #{pr_number}")
        print(f"  Branch: {branch_name}")
        return 0

    # Set up execution context for the rework workflow (PRD-225.4)
    return 0


def _get_merged_prd_prs() -> list[dict[str, Any]]:
    """Return merged PRs whose head branch matches ``prd/PRD-*``."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--json",
            "headRefName,mergedAt,mergeCommit,number",
            "--limit",
            "200",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"gh pr list failed: {result.stderr.strip()}")
    prs: list[dict[str, Any]] = json.loads(result.stdout)
    return [pr for pr in prs if re.match(r"^prd/PRD-", pr["headRefName"])]


def _find_prd_file_for_branch(branch_name: str, prd_dir: Path) -> Path | None:
    """Return the PRD file for a branch like ``prd/PRD-224.7-reconcile-status``."""
    m = re.match(r"^prd/(PRD-[\d.]+)", branch_name)
    if not m:
        return None
    prd_id = m.group(1)
    for f in sorted(prd_dir.glob(f"{prd_id}-*.md")):
        return f
    return None


def _get_prd_status(path: Path) -> str | None:
    """Read the ``status`` field from a PRD file's frontmatter."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^status:\s*(.+)$", line)
        if m:
            return m.group(1).strip().strip("\"'")
    return None


def _extract_prd_id_from_path(prd_file: Path) -> str:
    """Extract the PRD ID (e.g. ``PRD-224.7``) from a filename."""
    m = re.match(r"^(PRD-[\d.]+)-", prd_file.name)
    return m.group(1) if m else prd_file.stem


def _merge_commit_is_ancestor(pr: dict[str, Any], repo_root: Path) -> bool:
    """Check whether the PR's merge commit is reachable from HEAD.

    Returns True if the merge commit is an ancestor of HEAD (changes are
    present), False if it is missing (changes may have been clobbered).
    When the merge commit SHA is unavailable, returns True to avoid blocking.
    """
    merge_commit = pr.get("mergeCommit") or {}
    sha = merge_commit.get("oid")
    if not sha:
        return False  # can't verify — treat as suspicious
    result = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True,
    )
    return result.returncode == 0


def _build_reconcile_commit_msg(
    candidates: list[tuple[Path, dict[str, Any]]],
) -> str:
    """Build the commit message for a reconcile operation."""
    if len(candidates) == 1:
        prd_file, pr = candidates[0]
        prd_id = _extract_prd_id_from_path(prd_file)
        return (
            f"chore(prd): mark {prd_id} done "
            f"(auto-reconciled from merged PR #{pr['number']}) [skip ci]"
        )
    return f"chore(prd): reconcile {len(candidates)} merged PRD statuses [skip ci]"


def _commit_to_main(
    candidates: list[tuple[Path, dict[str, Any]]],
    repo_root: Path,
) -> None:
    """Stage changed PRD files and commit directly to main."""
    files = [str(c[0]) for c in candidates]
    subprocess.run(["git", "-C", str(repo_root), "add"] + files, check=True)
    msg = _build_reconcile_commit_msg(candidates)
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", msg],
        check=True,
    )


def _create_reconcile_pr(
    candidates: list[tuple[Path, dict[str, Any]]],
    repo_root: Path,
) -> None:
    """Create a PR with the reconciled status changes."""
    branch = "prd/reconcile-status"
    # Delete stale branch from a previous run, if any.
    subprocess.run(
        ["git", "-C", str(repo_root), "branch", "-D", branch],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "checkout", "-b", branch],
        check=True,
    )
    files = [str(c[0]) for c in candidates]
    subprocess.run(["git", "-C", str(repo_root), "add"] + files, check=True)
    msg = _build_reconcile_commit_msg(candidates)
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", msg],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "push", "-u", "origin", branch],
        check=True,
    )
    subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            msg,
            "--body",
            "Auto-reconciled by `prd reconcile`",
        ],
        check=True,
    )


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Find merged-but-not-flipped PRDs and reconcile their status."""
    prd_dir = args.prd_dir

    # 1. Get merged PRs with prd/* branches.
    merged_prs = _get_merged_prd_prs()

    # 2. Find corresponding PRD files still in 'review'.
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for pr in merged_prs:
        prd_file = _find_prd_file_for_branch(pr["headRefName"], prd_dir)
        if prd_file is None:
            continue
        if _get_prd_status(prd_file) == "review":
            candidates.append((prd_file, pr))

    if not candidates:
        print("All PRD statuses are up to date.")
        return 0

    # 2b. Verify merge commits are reachable from HEAD.
    repo_root = _find_repo_root(prd_dir)
    verified: list[tuple[Path, dict[str, Any]]] = []
    clobbered: list[tuple[Path, dict[str, Any]]] = []
    for prd_file, pr in candidates:
        if _merge_commit_is_ancestor(pr, repo_root):
            verified.append((prd_file, pr))
        else:
            clobbered.append((prd_file, pr))

    if clobbered:
        print("WARNING: The following PRDs were merged but their merge commits")
        print("are NOT reachable from HEAD — changes may have been clobbered:\n")
        for prd_file, pr in clobbered:
            prd_id = _extract_prd_id_from_path(prd_file)
            sha = (pr.get("mergeCommit") or {}).get("oid", "???")[:10]
            print(
                f"  {prd_id}: PR #{pr['number']} merge commit {sha} missing from HEAD"
            )
        print()

    candidates = verified

    if not candidates:
        print("No PRDs to reconcile (all candidates have missing merge commits).")
        return 0

    # 3. Print what would change (dry-run).
    for prd_file, pr in candidates:
        prd_id = _extract_prd_id_from_path(prd_file)
        print(f"  {prd_id}: review -> done (from merged PR #{pr['number']})")

    if not args.execute:
        print("\nDry run. Use --execute to apply changes.")
        return 0

    # 4. Apply changes.
    today = date.today().isoformat()
    for prd_file, _pr in candidates:
        update_frontmatter_field_at(
            prd_file, {"status": "done", "updated": f"'{today}'"}
        )

    # 5. Commit.
    if args.commit_to_main:
        _commit_to_main(candidates, repo_root)
    else:
        _create_reconcile_pr(candidates, repo_root)

    return 0


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
