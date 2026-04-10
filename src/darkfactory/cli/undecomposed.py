"""CLI subcommand: prd undecomposed."""

from __future__ import annotations

import argparse

from darkfactory import containment
from darkfactory.cli._shared import _load
from darkfactory.prd import parse_id_sort_key


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
