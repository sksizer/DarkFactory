"""System builtin: discuss_prd — launch interactive Claude Code session for a discussion phase."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from darkfactory.builtins.system_builtins import _register
from darkfactory.system import SystemContext


def _print_phase_banner(phase: str) -> None:
    """Print a phase banner to stderr."""
    bar = "\u2500" * 37
    print(bar, file=sys.stderr)
    print(f" Phase: {phase}", file=sys.stderr)
    print(" Press Ctrl-C now to abort the chain.", file=sys.stderr)
    print(bar, file=sys.stderr)


def _spawn_claude(prompt: str, cwd: Path) -> int:
    """Spawn an interactive Claude Code session. Returns the exit code.

    Extracted for testability — tests monkeypatch this function.
    """
    result = subprocess.run(
        ["claude", prompt],
        cwd=str(cwd),
        check=False,
    )
    return result.returncode


@_register("discuss_prd")
def discuss_prd(
    ctx: SystemContext,
    *,
    phase: str,
    prompt_file: str,
) -> None:
    """Launch an interactive Claude Code session for a discussion phase."""
    prd_context = ctx._shared_state.get("prd_context", "")
    if not prd_context:
        ctx.logger.warning(
            "discuss_prd: no PRD context in shared state, proceeding with empty context"
        )

    op_dir = ctx.operation.operation_dir
    if op_dir is not None:
        prompt_path = op_dir / prompt_file
    else:
        pkg_dir = Path(__file__).resolve().parent.parent / "commands" / "discuss"
        prompt_path = pkg_dir / prompt_file

    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt file not found: {prompt_path}")

    raw_prompt = prompt_path.read_text(encoding="utf-8")
    composed = raw_prompt.replace("{PRD_CONTEXT}", prd_context).replace(
        "{PHASE}", phase
    )

    _print_phase_banner(phase)
    time.sleep(1)

    exit_code = _spawn_claude(composed, ctx.cwd)

    if exit_code != 0:
        ctx.logger.warning(
            "discuss_prd: claude exited with code %d during %s phase (continuing)",
            exit_code,
            phase,
        )
