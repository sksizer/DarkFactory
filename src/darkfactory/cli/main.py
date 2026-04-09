"""Entry point for the CLI package."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from darkfactory.cli._parser import build_parser
from darkfactory.discovery import resolve_project_root
from darkfactory.style import Styler, resolve_style_config


def _configure_logging(verbose: bool) -> None:
    """Set up the harness logger so subprocess streaming + status updates
    actually appear in the user's terminal.

    Without this call, Python's logging defaults to WARNING — meaning
    every ``log.info(...)`` call inside ``invoke_claude`` (the streaming
    agent output) is silently dropped. The runner's progress dots are
    printed via ``print``, not ``logging``, so they were the only signal
    of life. Adding basicConfig once at CLI entry connects the streaming
    pipeline to the terminal.

    Verbose mode also enables DEBUG so internal harness diagnostics
    become visible.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,  # override any prior handler installed by an earlier import
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=getattr(args, "verbose", False))

    darkfactory_dir: Path | None = None
    if args.subcommand != "init" and (
        args.prd_dir is None or args.workflows_dir is None
    ):
        darkfactory_dir = resolve_project_root(
            cli_dir=getattr(args, "directory", None),
        )
        if darkfactory_dir is None:
            print(
                "No `.darkfactory/` directory found. Run `prd init` to set up this project.",
                file=sys.stderr,
            )
            return 1
        if args.prd_dir is None:
            args.prd_dir = darkfactory_dir / "prds"
        if args.workflows_dir is None:
            args.workflows_dir = darkfactory_dir / "workflows"

    # Derive operations_dir from prd_dir's parent (.darkfactory/) if not explicit.
    if getattr(args, "operations_dir", None) is None:
        if darkfactory_dir is not None:
            args.operations_dir = darkfactory_dir / "operations"
        else:
            args.operations_dir = args.prd_dir.parent / "operations"

    repo_root = darkfactory_dir.parent if darkfactory_dir is not None else None

    # Resolve style config and create a Styler. Any command module that needs
    # styled output reads args.styler — it never constructs one itself.
    # JSON-output paths must NOT call styler.render() — they use plain print().
    style_config = resolve_style_config(
        theme=getattr(args, "theme", None),
        icon_set=getattr(args, "icon_set", None),
        no_color=getattr(args, "no_color", False),
        repo_root=repo_root,
    )
    args.styler = Styler(style_config)

    func: Any = args.func
    return int(func(args))
