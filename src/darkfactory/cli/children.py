"""CLI subcommand: prd children."""

from __future__ import annotations

import argparse

from darkfactory import containment
from darkfactory.cli._shared import _format_prd_line, _load, _resolve_prd_or_exit


def cmd_children(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
    _resolve_prd_or_exit(args.prd_id, prds)
    kids = containment.children(args.prd_id, prds)
    if not kids:
        print("(no children)")
        return 0
    for kid in kids:
        print(_format_prd_line(kid, ("kind", "status")))
    return 0
