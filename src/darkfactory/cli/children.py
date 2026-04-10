"""CLI subcommand: prd children."""

from __future__ import annotations

import argparse

from darkfactory import containment
from darkfactory.cli._shared import _load


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
