"""Next command — list the next actionable PRDs."""

from __future__ import annotations

import argparse

from darkfactory import containment, graph
from darkfactory.cli._shared import (
    _action_sort_key,
    _emit_json,
    _format_prd_line,
    _load,
    _prd_to_dict,
)


def cmd_next(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
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
        return _emit_json(
            [
                _prd_to_dict(
                    p, ("id", "title", "priority", "effort", "capability", "kind")
                )
                for p in actionable
            ]
        )

    if not actionable:
        print("(no actionable PRDs match)")
        return 0
    for prd in actionable:
        print(_format_prd_line(prd, ("priority", "effort", "capability")))
    return 0
