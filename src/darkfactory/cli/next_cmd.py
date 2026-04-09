"""Next command — list the next actionable PRDs."""

from __future__ import annotations

import argparse
import json

from darkfactory import containment, graph
from darkfactory.cli._shared import _action_sort_key, _load


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
