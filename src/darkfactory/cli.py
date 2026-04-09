"""Command-line interface for the darkfactory PRD harness.

Usage::

    uv run prd <subcommand> [options]

Defaults: PRDs live in ``prds/`` and workflows in ``workflows/`` at the
repo root. Override via ``--prd-dir`` and ``--workflows-dir``.

This should have minimial logic; the subcommand implementations can call into
specific modules for the heavy lifting.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from . import assign, checks, containment, graph, impacts
from .discovery import resolve_project_root
from .checks import StaleWorktree, find_stale_worktrees, is_safe_to_remove
from .graph_execution import RunEvent, execute_graph, plan_execution
from .invoke import capability_to_model
from .loader import load_workflows
from .prd import (
    PRD,
    PRD_ID_RE,
    dump_frontmatter,
    load_all,
    normalize_list_field_at,
    parse_id_sort_key,
    set_workflow,
    update_frontmatter_field_at,
)
from .runner import _compute_branch_name, _pick_model, run_workflow
from .style import Element, Styler, resolve_style_config
from .workflow import AgentTask, BuiltIn, ShellTask, Task, Workflow

# Priority/effort orderings used for sorting actionable lists.
PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
EFFORT_ORDER: dict[str, int] = {"xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4}
CAPABILITY_ORDER: dict[str, int] = {
    "trivial": 0,
    "simple": 1,
    "moderate": 2,
    "complex": 3,
}


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


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a ``.git`` directory is found.

    Used for git-specific operations (worktrees, tracked files, branches).
    Project discovery uses ``resolve_project_root`` from ``discovery`` instead.
    """
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise SystemExit(f"could not locate git repo root from {start}")


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


def _slugify(title: str) -> str:
    """Convert a title to kebab-case slug."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug or "untitled"


def _next_flat_prd_id(prds: dict[str, PRD]) -> str:
    """Find the next unused flat PRD id (PRD-NNN) above the existing max."""
    flat_ids = [
        int(pid.removeprefix("PRD-")) for pid in prds if re.match(r"^PRD-\d+$", pid)
    ]
    next_n = (max(flat_ids) + 1) if flat_ids else 1
    return f"PRD-{next_n:03d}"


DRAFT_TEMPLATE_BODY = """# {title}

## Summary

<!-- 1-3 sentence elevator pitch. What does this deliver and why does it matter? -->

## Motivation

<!-- What problem does this solve? Who benefits? What happens if we don't build it? -->

## Requirements

### Functional

1. ...

### Non-Functional

1. ...

## Technical Approach

<!-- High-level design: affected modules, data flow, key libraries. -->

## Acceptance Criteria

- [ ] AC-1: ...

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

## References

"""


def cmd_new(args: argparse.Namespace) -> int:
    prds = load_all(args.prd_dir) if args.prd_dir.exists() else {}

    # Pick ID
    if args.id:
        if not PRD_ID_RE.match(args.id):
            raise SystemExit(f"invalid PRD id: {args.id!r}")
        if args.id in prds:
            raise SystemExit(f"PRD id {args.id!r} already exists")
        new_id = args.id
    else:
        new_id = _next_flat_prd_id(prds)

    slug = _slugify(args.title)
    filename = f"{new_id}-{slug}.md"
    path = args.prd_dir / filename
    if path.exists():
        raise SystemExit(f"file already exists: {path}")

    today = date.today().isoformat()
    frontmatter = {
        "id": new_id,
        "title": args.title,
        "kind": args.kind,
        "status": "draft",
        "priority": args.priority,
        "effort": args.effort,
        "capability": args.capability,
        "parent": None,
        "depends_on": [],
        "blocks": [],
        "impacts": [],
        "workflow": None,
        "assignee": None,
        "reviewers": [],
        "target_version": None,
        "created": today,
        "updated": today,
        "tags": [],
    }

    body = DRAFT_TEMPLATE_BODY.format(title=args.title)
    content = f"---\n{dump_frontmatter(frontmatter)}---\n\n{body}"

    args.prd_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Created {path}")

    if args.open:
        editor = os.environ.get("EDITOR", "")
        if editor:
            subprocess.run([editor, str(path)], check=False)

    return 0


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
                {
                    "id": p.id,
                    "title": p.title,
                    "priority": p.priority,
                    "effort": p.effort,
                }
                for p in runnable[:5]
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"PRDs — {len(prds)} total")
    for status in (
        "done",
        "review",
        "in-progress",
        "ready",
        "blocked",
        "draft",
        "cancelled",
    ):
        n = counts.get(status, 0)
        if n:
            print(f"  {status:14} {n}")
    print(f"\n  actionable: {len(actionable)}   runnable: {len(runnable)}")
    if runnable:
        print("\nNext runnable (top 5):")
        for prd in runnable[:5]:
            print(
                f"  {prd.id:14} [{prd.kind}/{prd.effort}/{prd.capability}]  {prd.title}"
            )

    try:
        repo_root = _find_repo_root(args.prd_dir)
        stale = find_stale_worktrees(repo_root)
        if stale:
            print(
                f"\n{len(stale)} worktrees for merged PRDs"
                " (run 'prd cleanup --merged' to remove)"
            )
    except (SystemExit, Exception):  # noqa: BLE001 — best-effort outside a git repo
        pass

    return 0


def _remove_worktree(worktree: StaleWorktree, repo_root: Path) -> None:
    """Remove a worktree directory and delete the local branch."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree.worktree_path)],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-D", worktree.branch.removeprefix("prd/")],
        cwd=repo_root,
        capture_output=True,
    )


def _find_worktree_for_prd(prd_id: str, repo_root: Path) -> StaleWorktree | None:
    """Find the worktree entry for the given PRD id, regardless of PR state."""
    worktrees_dir = repo_root / ".worktrees"
    if not worktrees_dir.exists():
        return None
    for entry in sorted(worktrees_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        m = re.match(r"^(PRD-[\d.]+)", name)
        if not m:
            continue
        if m.group(1) != prd_id:
            continue
        branch = f"prd/{name}"
        pr_state = checks._get_pr_state(branch, repo_root)
        return StaleWorktree(
            prd_id=prd_id,
            branch=branch,
            worktree_path=entry,
            pr_state=pr_state,
        )
    return None


def _cleanup_single(prd_id: str, force: bool, repo_root: Path) -> int:
    worktree = _find_worktree_for_prd(prd_id, repo_root)
    if worktree is None:
        print(f"No worktree found for {prd_id}")
        return 1
    status = is_safe_to_remove(worktree, force=force)
    if not status.safe:
        print(f"Cannot remove {prd_id}: {status.reason}")
        return 1
    _remove_worktree(worktree, repo_root)
    print(f"Removed worktree and branch for {prd_id}")
    return 0


def _cleanup_merged(force: bool, repo_root: Path) -> int:
    stale = find_stale_worktrees(repo_root)
    if not stale:
        print("No stale worktrees found")
        return 0
    removed = 0
    skipped = 0
    for worktree in stale:
        status = is_safe_to_remove(worktree, force=force)
        if not status.safe:
            print(f"Skipping {worktree.prd_id}: {status.reason}")
            skipped += 1
            continue
        _remove_worktree(worktree, repo_root)
        print(f"Removed {worktree.prd_id}")
        removed += 1
    print(f"Removed {removed}, skipped {skipped}")
    return 0 if skipped == 0 else 1


def _cleanup_all(force: bool, repo_root: Path) -> int:
    worktrees_dir = repo_root / ".worktrees"
    if not worktrees_dir.exists():
        print("No .worktrees directory found")
        return 0

    all_worktrees: list[StaleWorktree] = []
    for entry in sorted(worktrees_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        m = re.match(r"^(PRD-[\d.]+)", name)
        if not m:
            continue
        prd_id = m.group(1)
        branch = f"prd/{name}"
        pr_state = checks._get_pr_state(branch, repo_root)
        all_worktrees.append(
            StaleWorktree(
                prd_id=prd_id,
                branch=branch,
                worktree_path=entry,
                pr_state=pr_state,
            )
        )

    if not all_worktrees:
        print("No worktrees found")
        return 0

    open_prs = [w for w in all_worktrees if w.pr_state == "OPEN"]
    if open_prs:
        print(f"Warning: {len(open_prs)} worktree(s) have open PRs:")
        for w in open_prs:
            print(f"  {w.prd_id} ({w.branch})")

    confirm = (
        input(f"Remove all {len(all_worktrees)} worktree(s)? [y/N] ").strip().lower()
    )
    if confirm not in ("y", "yes"):
        print("Aborted")
        return 1

    removed = 0
    skipped = 0
    for worktree in all_worktrees:
        status = is_safe_to_remove(worktree, force=force)
        if not status.safe:
            print(f"Skipping {worktree.prd_id}: {status.reason}")
            skipped += 1
            continue
        _remove_worktree(worktree, repo_root)
        print(f"Removed {worktree.prd_id}")
        removed += 1
    print(f"Removed {removed}, skipped {skipped}")
    return 0 if skipped == 0 else 1


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Remove worktrees for completed PRDs."""
    repo_root = _find_repo_root(args.prd_dir)
    prd_id: str | None = getattr(args, "prd_id", None)
    merged: bool = getattr(args, "merged", False)
    all_: bool = getattr(args, "all_", False)
    force: bool = getattr(args, "force", False)

    if prd_id:
        return _cleanup_single(prd_id, force, repo_root)
    elif merged:
        return _cleanup_merged(force, repo_root)
    elif all_:
        return _cleanup_all(force, repo_root)
    else:
        print("Specify PRD-X, --merged, or --all")
        return 1


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
        print(
            f"{prd.id:14} [{prd.priority}/{prd.effort}/{prd.capability}]  {prd.title}"
        )
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
    print(f"  workflow:   {workflow.name} (priority {workflow.priority})")
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

    - **Single leaf with deps satisfied:** legacy path — one worktree,
      one workflow run.
    - **Epic/feature with children, or leaf with unmet deps:** graph
      execution — walks the DAG in topological order, running each
      actionable leaf in its own worktree. Sequential only (PRD-220).
      Parallel fan-out is PRD-551.
    """
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    prd = prds[args.prd_id]

    workflows = _load_workflows_or_fail(args.workflows_dir)

    repo_root = _find_repo_root(args.prd_dir)
    base_ref = _resolve_base_ref(args.base, repo_root)
    dry_run = not args.execute
    styler: Styler = args.styler

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
            "headRefName,mergedAt,number",
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
    repo_root = _find_repo_root(prd_dir)
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


# ---------- argparse plumbing ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prd", description="Pumice PRD harness CLI")
    parser.add_argument(
        "--directory",
        "-C",
        type=Path,
        default=None,
        metavar="DIR",
        help="Project root containing .darkfactory/ (overrides DARKFACTORY_DIR env and walk-up)",
    )
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
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON output where supported"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--theme",
        default=None,
        choices=["dark", "light"],
        help="Color theme (default: dark)",
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        default=False,
        help="Disable all color output",
    )
    parser.add_argument(
        "--icon-set",
        dest="icon_set",
        default=None,
        choices=["nerdfont", "ascii", "emoji"],
        help="Icon set to use (default: auto-detected, ascii fallback)",
    )

    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub_new = sub.add_parser("new", help="Create a new draft PRD from a template")
    sub_new.add_argument("title", help="PRD title (positional)")
    sub_new.add_argument(
        "--id", default=None, help="Explicit PRD id (default: next flat id)"
    )
    sub_new.add_argument(
        "--kind", default="task", choices=["epic", "feature", "component", "task"]
    )
    sub_new.add_argument(
        "--priority", default="medium", choices=["critical", "high", "medium", "low"]
    )
    sub_new.add_argument("--effort", default="m", choices=["xs", "s", "m", "l", "xl"])
    sub_new.add_argument(
        "--capability",
        default="moderate",
        choices=["trivial", "simple", "moderate", "complex"],
    )
    sub_new.add_argument(
        "--open",
        action="store_true",
        help="Open the new file in $EDITOR after creation",
    )
    sub_new.set_defaults(func=cmd_new)

    sub_status = sub.add_parser("status", help="DAG overview and counts")
    sub_status.set_defaults(func=cmd_status)

    sub_cleanup = sub.add_parser("cleanup", help="Remove worktrees for completed PRDs")
    sub_cleanup.add_argument(
        "prd_id",
        nargs="?",
        default=None,
        help="PRD id to clean up (e.g. PRD-224.4)",
    )
    sub_cleanup.add_argument(
        "--merged",
        action="store_true",
        help="Remove all worktrees for merged-PR PRDs",
    )
    sub_cleanup.add_argument(
        "--all",
        dest="all_",
        action="store_true",
        help="Remove all worktrees (with confirmation prompt)",
    )
    sub_cleanup.add_argument(
        "--force",
        action="store_true",
        help="Remove even if there are unpushed commits",
    )
    sub_cleanup.set_defaults(func=cmd_cleanup)

    sub_next = sub.add_parser("next", help="List actionable PRDs")
    sub_next.add_argument("--limit", type=int, default=10)
    sub_next.add_argument(
        "--capability", default="", help="Comma-separated capability filter"
    )
    sub_next.set_defaults(func=cmd_next)

    sub_validate = sub.add_parser("validate", help="Cycle/missing-dep/orphan checks")
    sub_validate.set_defaults(func=cmd_validate)

    sub_tree = sub.add_parser("tree", help="Show containment tree")
    sub_tree.add_argument(
        "prd_id", nargs="?", help="Root PRD id (default: full forest)"
    )
    sub_tree.set_defaults(func=cmd_tree)

    sub_children = sub.add_parser("children", help="Direct children of a PRD")
    sub_children.add_argument("prd_id")
    sub_children.set_defaults(func=cmd_children)

    sub_orphans = sub.add_parser("orphans", help="Top-level PRDs (no parent)")
    sub_orphans.set_defaults(func=cmd_orphans)

    sub_undec = sub.add_parser(
        "undecomposed", help="Epics/features lacking task children"
    )
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

    sub_normalize = sub.add_parser(
        "normalize",
        help="Canonicalize list fields (tags, impacts, depends_on, blocks)",
    )
    sub_normalize.add_argument(
        "prd_id",
        nargs="?",
        help="PRD id to normalize (e.g. PRD-070); required unless --all",
    )
    sub_normalize.add_argument(
        "--all",
        action="store_true",
        help="Normalize every PRD in the directory",
    )
    sub_normalize.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any file would change without writing",
    )
    sub_normalize.set_defaults(func=cmd_normalize)

    sub_plan = sub.add_parser(
        "plan",
        help="Show the execution plan for a PRD without touching anything",
    )
    sub_plan.add_argument("prd_id")
    sub_plan.add_argument(
        "--workflow",
        default=None,
        help="Override the workflow assignment (by name)",
    )
    sub_plan.add_argument(
        "--base",
        default=None,
        help="Base ref for the new branch (default: current HEAD)",
    )
    sub_plan.add_argument(
        "--model",
        default=None,
        help="Override the capability->model mapping (e.g. opus)",
    )
    sub_plan.set_defaults(func=cmd_plan)

    sub_run = sub.add_parser(
        "run",
        help="Run a workflow against a PRD (dry-run unless --execute)",
    )
    sub_run.add_argument("prd_id")
    sub_run.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute (default is dry-run)",
    )
    sub_run.add_argument(
        "--workflow",
        default=None,
        help="Override the workflow assignment (by name)",
    )
    sub_run.add_argument(
        "--base",
        default=None,
        help="Base ref for the new branch (default: current HEAD)",
    )
    sub_run.add_argument(
        "--model",
        default=None,
        help="Override the capability->model mapping (e.g. opus)",
    )
    sub_run.add_argument(
        "--max-runs",
        type=int,
        default=None,
        dest="max_runs",
        help=(
            "In graph mode, cap the total number of PRD runs this "
            "invocation may execute (counts successes, failures, and "
            "mid-run introduced PRDs). Default: unbounded."
        ),
    )
    sub_run.add_argument(
        "--timeout",
        type=int,
        default=None,
        dest="timeout",
        help="Override timeout in minutes (overrides all other timeout sources)",
    )
    sub_run.set_defaults(func=cmd_run)

    sub_reconcile = sub.add_parser(
        "reconcile",
        help="Find merged-but-not-flipped PRDs and reconcile their status",
    )
    sub_reconcile.add_argument(
        "--execute",
        action="store_true",
        help="Apply the status updates (default is dry-run)",
    )
    sub_reconcile.add_argument(
        "--commit-to-main",
        dest="commit_to_main",
        action="store_true",
        default=False,
        help="Commit directly to main instead of opening a PR",
    )
    sub_reconcile.set_defaults(func=cmd_reconcile)

    return parser


def _configure_logging(verbose: bool) -> None:
    """Set up the harness logger so subprocess streaming + status updates
    actually appear in the user's terminal.

    Without this call, Python's logging defaults to WARNING — meaning
    every ``log.info(...)`` call inside ``invoke_claude`` (the streaming
    agent output) is silently dropped. The runner's progress dots are
    printed via ``print``, not ``logging``, so they were the only signal
    of life. Adding basicConfig once at CLI entry connects the streaming
    pipeline to the terminal.

    Verbose mode also enables DEBUG so internal harness diagnostics
    become visible.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,  # override any prior handler installed by an earlier import
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=getattr(args, "verbose", False))

    darkfactory_dir: Path | None = None
    if args.prd_dir is None or args.workflows_dir is None:
        darkfactory_dir = resolve_project_root(
            cli_dir=getattr(args, "directory", None),
        )
        if darkfactory_dir is None:
            print(
                "No `.darkfactory/` directory found. Run `prd init` to set up this project.",
                file=sys.stderr,
            )
            return 1
        if args.prd_dir is None:
            args.prd_dir = darkfactory_dir / "prds"
        if args.workflows_dir is None:
            args.workflows_dir = darkfactory_dir / "workflows"

    repo_root = darkfactory_dir.parent if darkfactory_dir is not None else None

    # Resolve style config and create a Styler. Any command module that needs
    # styled output reads args.styler — it never constructs one itself.
    # JSON-output paths must NOT call styler.render() — they use plain print().
    style_config = resolve_style_config(
        theme=getattr(args, "theme", None),
        icon_set=getattr(args, "icon_set", None),
        no_color=getattr(args, "no_color", False),
        repo_root=repo_root,
    )
    args.styler = Styler(style_config)

    func: Any = args.func
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
