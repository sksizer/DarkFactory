"""cmd_discuss — interactive PRD discussion via phased Claude Code chain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from darkfactory.cli._shared import _find_repo_root, _load, _resolve_prd_or_exit
from darkfactory.commands.discuss import discuss_operation
from darkfactory.engine import CodeEnv, ProjectRun
from darkfactory.runner import run_project_operation
from darkfactory.workflow import RunContext
from darkfactory.utils.system import check_prerequisites


def launch_discuss_for_prd(prd_id: str, args: argparse.Namespace) -> int:
    """Build context and run the discuss operation for a given PRD id.

    Shared entry point used by both ``cmd_discuss`` and ``prd new --discuss``.
    """
    cwd = Path.cwd()
    check_prerequisites(args.data_dir.parent if hasattr(args, "data_dir") else cwd)

    prds = _load(args.data_dir)
    _resolve_prd_or_exit(prd_id, prds)

    repo_root = _find_repo_root(args.data_dir)

    pkg_dir = Path(__file__).resolve().parent.parent / "commands" / "discuss"

    op = discuss_operation
    op.workflow_dir = pkg_dir

    ctx = RunContext(dry_run=False)
    ctx.state.put(CodeEnv(repo_root=repo_root, cwd=repo_root))
    ctx.state.put(
        ProjectRun(
            workflow=op,
            prds=prds,
            targets=tuple(prds.keys()),
            target_prd=prd_id,
        )
    )

    result = run_project_operation(op, ctx)
    if not result.success:
        print(f"discuss chain failed: {result.failure_reason}", file=sys.stderr)
        return 1
    return 0


def cmd_discuss(args: argparse.Namespace) -> int:
    """Entry point for ``prd discuss <prd-id>``."""
    return launch_discuss_for_prd(args.prd_id, args)
