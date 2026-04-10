"""CLI subcommand: prd status."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from darkfactory import containment, graph
from darkfactory.checks import find_stale_worktrees
from darkfactory.cli._shared import _action_sort_key, _find_repo_root, _load


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
        "superseded",
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
