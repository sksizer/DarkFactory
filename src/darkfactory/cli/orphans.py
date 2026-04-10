"""CLI subcommand: prd orphans."""

from __future__ import annotations

import argparse

from darkfactory import containment
from darkfactory.cli._shared import _load


def cmd_orphans(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    rs = containment.roots(prds)
    for prd in rs:
        print(f"{prd.id:14} [{prd.kind}/{prd.status}]  {prd.title}")
    return 0
