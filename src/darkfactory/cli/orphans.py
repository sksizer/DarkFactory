"""CLI subcommand: prd orphans."""

from __future__ import annotations

import argparse

from darkfactory import containment
from darkfactory.cli._shared import _format_prd_line, _load


def cmd_orphans(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
    rs = containment.roots(prds)
    for prd in rs:
        print(_format_prd_line(prd, ("kind", "status")))
    return 0
