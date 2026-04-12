"""CLI subcommand: prd status."""

from __future__ import annotations

import argparse
from collections import Counter

from darkfactory import graph
from darkfactory.graph import containment
from darkfactory.checks import find_stale_worktrees
from darkfactory.cli._shared import (
    _action_sort_key,
    _emit_json,
    _find_repo_root,
    _format_prd_line,
    _load,
    _prd_to_dict,
)


def cmd_status(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
    counts = Counter(prd.status for prd in prds.values())
    actionable = sorted(
        (prd for prd in prds.values() if graph.is_actionable(prd, prds)),
        key=_action_sort_key,
    )
    runnable = [prd for prd in actionable if containment.is_runnable(prd, prds)]

    if args.json:
        return _emit_json(
            {
                "total": len(prds),
                "by_status": dict(counts),
                "actionable": len(actionable),
                "runnable": len(runnable),
                "next": [
                    _prd_to_dict(p, ("id", "title", "priority", "effort"))
                    for p in runnable[:5]
                ],
            }
        )

    print(f"PRDs — {len(prds)} total")
    for status in (
        "done",
        "review",
        "in-progress",
        "ready",
        "blocked",
        "draft",
        "cancelled",
        "superseded",
    ):
        n = counts.get(status, 0)
        if n:
            print(f"  {status:14} {n}")
    print(f"\n  actionable: {len(actionable)}   runnable: {len(runnable)}")
    if runnable:
        print("\nNext runnable (top 5):")
        for prd in runnable[:5]:
            print("  " + _format_prd_line(prd, ("kind", "effort", "capability")))

    try:
        repo_root = _find_repo_root(args.data_dir)
        stale = find_stale_worktrees(repo_root)
        if stale:
            print(
                f"\n{len(stale)} worktrees for merged PRDs"
                " (run 'prd cleanup --merged' to remove)"
            )
    except (SystemExit, Exception):  # noqa: BLE001 — best-effort outside a git repo
        pass

    return 0
