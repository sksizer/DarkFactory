"""CLI subcommand: prd undecomposed."""

from __future__ import annotations

import argparse

from darkfactory.graph import containment
from darkfactory.cli._shared import _format_prd_line, _load
from darkfactory.model import parse_id_sort_key


def cmd_undecomposed(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
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
        print(_format_prd_line(prd, ("kind",)))
    return 0
