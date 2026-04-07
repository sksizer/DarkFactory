"""Command-line interface for the PRD harness.

Foundation phase: read-only subcommands only. Workflow execution, migration,
and ``run``/``run-chain`` land in subsequent commits.

Usage::

    uv run --project tools/prd-harness prd <subcommand> [options]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from . import assign, containment, graph, impacts
from .loader import load_workflows
from .prd import PRD, load_all, parse_id_sort_key, set_workflow
from .workflow import Workflow

# Priority/effort orderings used for sorting actionable lists.
PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
EFFORT_ORDER: dict[str, int] = {"xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4}
CAPABILITY_ORDER: dict[str, int] = {
    "trivial": 0,
    "simple": 1,
    "moderate": 2,
    "complex": 3,
}


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a ``.git`` directory is found."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise SystemExit(f"could not locate git repo root from {start}")


def _default_prd_dir() -> Path:
    """Locate ``docs/prd/`` relative to the repo root."""
    repo = _find_repo_root(Path.cwd())
    return repo / "docs" / "prd"


def _default_workflows_dir() -> Path:
    """Locate ``tools/prd-harness/workflows/`` relative to the repo root.

    All built-in workflows ship under this path. Overridable via
    ``--workflows-dir`` on the CLI for tests or alternative deployments.
    """
    repo = _find_repo_root(Path.cwd())
    return repo / "tools" / "prd-harness" / "workflows"


def _load_workflows_or_fail(workflows_dir: Path) -> dict[str, Workflow]:
    """Load workflows with a user-friendly error if the directory is missing."""
    if not workflows_dir.exists():
        raise SystemExit(f"workflows directory not found: {workflows_dir}")
    return load_workflows(workflows_dir)


def _action_sort_key(prd: PRD) -> tuple[int, int, tuple[int, ...]]:
    """Sort key for actionable lists: priority, effort, natural id."""
    return (
        PRIORITY_ORDER.get(prd.priority, 99),
        EFFORT_ORDER.get(prd.effort, 99),
        parse_id_sort_key(prd.id),
    )


def _load(prd_dir: Path) -> dict[str, PRD]:
    if not prd_dir.exists():
        raise SystemExit(f"PRD directory not found: {prd_dir}")
    return load_all(prd_dir)


# ---------- subcommand implementations ----------


def cmd_status(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    counts = Counter(prd.status for prd in prds.values())
    actionable = sorted(
        (prd for prd in prds.values() if graph.is_actionable(prd, prds)),
        key=_action_sort_key,
    )
    runnable = [prd for prd in actionable if containment.is_runnable(prd, prds)]

    if args.json:
        out = {
            "total": len(prds),
            "by_status": dict(counts),
            "actionable": len(actionable),
            "runnable": len(runnable),
            "next": [
                {"id": p.id, "title": p.title, "priority": p.priority, "effort": p.effort}
                for p in runnable[:5]
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"Pumice PRDs — {len(prds)} total")
    for status in ("done", "review", "in-progress", "ready", "blocked", "draft", "cancelled"):
        n = counts.get(status, 0)
        if n:
            print(f"  {status:14} {n}")
    print(f"\n  actionable: {len(actionable)}   runnable: {len(runnable)}")
    if runnable:
        print("\nNext runnable (top 5):")
        for prd in runnable[:5]:
            print(f"  {prd.id:14} [{prd.kind}/{prd.effort}/{prd.capability}]  {prd.title}")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    actionable = sorted(
        (prd for prd in prds.values() if graph.is_actionable(prd, prds)),
        key=_action_sort_key,
    )
    actionable = [prd for prd in actionable if containment.is_runnable(prd, prds)]
    if args.capability:
        wanted = {c.strip() for c in args.capability.split(",")}
        actionable = [prd for prd in actionable if prd.capability in wanted]
    actionable = actionable[: args.limit]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": p.id,
                        "title": p.title,
                        "priority": p.priority,
                        "effort": p.effort,
                        "capability": p.capability,
                        "kind": p.kind,
                    }
                    for p in actionable
                ],
                indent=2,
            )
        )
        return 0

    if not actionable:
        print("(no actionable PRDs match)")
        return 0
    for prd in actionable:
        print(f"{prd.id:14} [{prd.priority}/{prd.effort}/{prd.capability}]  {prd.title}")
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

    # 5. Impact overlap warnings (ready PRDs only)
    try:
        repo_root = _find_repo_root(args.prd_dir)
        files = impacts.tracked_files(repo_root)
    except Exception:  # noqa: BLE001 — best-effort outside a git repo
        files = []

    if files:
        ready = [p for p in prds.values() if p.status == "ready" and p.impacts]
        for i, a in enumerate(ready):
            for b in ready[i + 1 :]:
                # Skip if there's an explicit dep relation in either direction.
                if b.id in a.depends_on or a.id in b.depends_on:
                    continue
                overlap = impacts.impacts_overlap(a, b, files)
                if overlap:
                    warnings.append(
                        f"{a.id} and {b.id} have overlapping impacts "
                        f"({len(overlap)} files) but no explicit dependency"
                    )

    # 6. Undeclared impacts (informational)
    undeclared = [p.id for p in prds.values() if p.status == "ready" and not p.impacts]
    if undeclared and args.verbose:
        warnings.append(
            f"{len(undeclared)} ready PRDs have no declared impacts (undeclared = sequential)"
        )

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    for warn in warnings:
        print(f"WARN:  {warn}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(prds)} PRDs valid ({len(warnings)} warning(s))")
    return 0


def _print_tree(prd: PRD, prds: dict[str, PRD], prefix: str = "", is_last: bool = True) -> None:
    """Recursively print a containment tree branch."""
    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{prd.id}  [{prd.kind}/{prd.status}]  {prd.title}")
    extension = "    " if is_last else "│   "
    kids = containment.children(prd.id, prds)
    for i, kid in enumerate(kids):
        _print_tree(kid, prds, prefix + extension, i == len(kids) - 1)


def cmd_tree(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    if args.prd_id:
        prd = prds.get(args.prd_id)
        if prd is None:
            raise SystemExit(f"unknown PRD id: {args.prd_id}")
        print(f"{prd.id}  [{prd.kind}/{prd.status}]  {prd.title}")
        kids = containment.children(prd.id, prds)
        for i, kid in enumerate(kids):
            _print_tree(kid, prds, "", i == len(kids) - 1)
    else:
        for root in containment.roots(prds):
            print(f"{root.id}  [{root.kind}/{root.status}]  {root.title}")
            kids = containment.children(root.id, prds)
            for i, kid in enumerate(kids):
                _print_tree(kid, prds, "", i == len(kids) - 1)
            print()
    return 0


def cmd_children(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    kids = containment.children(args.prd_id, prds)
    if not kids:
        print("(no children)")
        return 0
    for kid in kids:
        print(f"{kid.id:14} [{kid.kind}/{kid.status}]  {kid.title}")
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

    if args.json:
        print(
            json.dumps(
                [
                    {"id": other_id, "files": sorted(files)}
                    for other_id, files in conflicts
                ],
                indent=2,
            )
        )
        return 0

    if not prd.impacts:
        print(f"{prd.id} has no declared impacts; cannot compute overlaps")
        return 0
    if not conflicts:
        print(f"{prd.id} has no impact conflicts with other PRDs")
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


# ---------- argparse plumbing ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prd", description="Pumice PRD harness CLI")
    parser.add_argument(
        "--prd-dir",
        type=Path,
        default=None,
        help="Path to docs/prd directory (default: auto-detect from cwd)",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=None,
        help="Path to workflows directory (default: tools/prd-harness/workflows)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output where supported")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub_status = sub.add_parser("status", help="DAG overview and counts")
    sub_status.set_defaults(func=cmd_status)

    sub_next = sub.add_parser("next", help="List actionable PRDs")
    sub_next.add_argument("--limit", type=int, default=10)
    sub_next.add_argument("--capability", default="", help="Comma-separated capability filter")
    sub_next.set_defaults(func=cmd_next)

    sub_validate = sub.add_parser("validate", help="Cycle/missing-dep/orphan checks")
    sub_validate.set_defaults(func=cmd_validate)

    sub_tree = sub.add_parser("tree", help="Show containment tree")
    sub_tree.add_argument("prd_id", nargs="?", help="Root PRD id (default: full forest)")
    sub_tree.set_defaults(func=cmd_tree)

    sub_children = sub.add_parser("children", help="Direct children of a PRD")
    sub_children.add_argument("prd_id")
    sub_children.set_defaults(func=cmd_children)

    sub_orphans = sub.add_parser("orphans", help="Top-level PRDs (no parent)")
    sub_orphans.set_defaults(func=cmd_orphans)

    sub_undec = sub.add_parser("undecomposed", help="Epics/features lacking task children")
    sub_undec.set_defaults(func=cmd_undecomposed)

    sub_conflicts = sub.add_parser("conflicts", help="Show file impact overlaps")
    sub_conflicts.add_argument("prd_id")
    sub_conflicts.set_defaults(func=cmd_conflicts)

    sub_list_wfs = sub.add_parser(
        "list-workflows", help="Show loaded workflows with priorities"
    )
    sub_list_wfs.set_defaults(func=cmd_list_workflows)

    sub_assign = sub.add_parser(
        "assign",
        help="Compute workflow assignment per PRD (optionally persist)",
    )
    sub_assign.add_argument(
        "--write",
        action="store_true",
        help="Persist assignments to PRD frontmatter (only for unassigned PRDs)",
    )
    sub_assign.set_defaults(func=cmd_assign)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.prd_dir is None:
        args.prd_dir = _default_prd_dir()
    if args.workflows_dir is None:
        args.workflows_dir = _default_workflows_dir()
    func: Any = args.func
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
