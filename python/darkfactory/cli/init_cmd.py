"""CLI subcommand: init — scaffold .darkfactory/ in the current project."""

from __future__ import annotations

import argparse
import sys

from darkfactory.config import init_project


def cmd_init(args: argparse.Namespace) -> int:
    from pathlib import Path

    target = (args.directory or Path.cwd()).resolve()
    try:
        msg = init_project(target)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(msg)
    return 0
