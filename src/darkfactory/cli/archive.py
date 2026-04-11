"""CLI subcommand: archive — move completed PRDs to the archive."""

from __future__ import annotations

import argparse
import sys

from darkfactory.model import archive, load_one


def cmd_archive(args: argparse.Namespace) -> int:
    """Move a terminal-state PRD to the archive directory."""
    try:
        prd = load_one(args.data_dir, args.prd_id)
    except KeyError:
        print(f"unknown PRD id: {args.prd_id}", file=sys.stderr)
        return 1
    try:
        result = archive(prd, args.data_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Archived {result.id} -> {result.path}")
    return 0
