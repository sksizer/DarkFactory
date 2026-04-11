"""cmd_discuss — interactive PRD discussion via phased Claude Code chain."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from darkfactory.cli._shared import _find_repo_root, _load, _resolve_prd_or_exit
from darkfactory.commands.discuss import discuss_operation
from darkfactory.system import SystemContext
from darkfactory.system_runner import run_system_operation


def _check_prerequisites(cwd: Path) -> None:
    """Fail fast if claude or git are missing, or cwd is not a git repo."""
    if shutil.which("claude") is None:
        raise SystemExit("error: 'claude' is not on PATH. Install Claude Code to use 'prd discuss'.")
    if shutil.which("git") is None:
        raise SystemExit("error: 'git' is not on PATH.")
    if not (cwd / ".git").exists():
        try:
            _find_repo_root(cwd)
        except SystemExit:
            raise SystemExit("error: current directory is not inside a git working tree.")


def launch_discuss_for_prd(prd_id: str, args: argparse.Namespace) -> int:
    """Build context and run the discuss operation for a given PRD id.

    Shared entry point used by both ``cmd_discuss`` and ``prd new --discuss``.
    """
    cwd = Path.cwd()
    _check_prerequisites(args.prd_dir.parent if hasattr(args, "prd_dir") else cwd)

    prds = _load(args.prd_dir)
    _resolve_prd_or_exit(prd_id, prds)

    repo_root = _find_repo_root(args.prd_dir)

    pkg_dir = Path(__file__).resolve().parent.parent / "commands" / "discuss"

    op = discuss_operation
    op.operation_dir = pkg_dir

    ctx = SystemContext(
        repo_root=repo_root,
        prds=prds,
        operation=op,
        cwd=repo_root,
        dry_run=False,
        target_prd=prd_id,
    )

    result = run_system_operation(op, ctx)
    if not result.success:
        print(f"discuss chain failed: {result.failure_reason}", file=sys.stderr)
        return 1
    return 0


def cmd_discuss(args: argparse.Namespace) -> int:
    """Entry point for ``prd discuss <prd-id>``."""
    return launch_discuss_for_prd(args.prd_id, args)
