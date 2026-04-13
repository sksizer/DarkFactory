"""Project builtin: discuss_prd — launch interactive Claude Code session for a discussion phase."""

from __future__ import annotations

import time
from pathlib import Path

from darkfactory.operations.project_builtins import _register
from darkfactory.engine import PrdContext
from darkfactory.workflow import RunContext
from darkfactory.utils.claude_code import EffortLevel, spawn_claude
from darkfactory.utils.tui import print_phase_banner


@_register("discuss_prd")
def discuss_prd(
    ctx: RunContext,
    *,
    phase: str,
    prompt_file: str,
    effort_level: EffortLevel | None = None,
) -> None:
    """Launch an interactive Claude Code session for a discussion phase."""
    prd_context = ""
    if ctx.state.has(PrdContext):
        prd_context = ctx.state.get(PrdContext).body
    if not prd_context:
        ctx.logger.warning(
            "discuss_prd: no PRD context in state, proceeding with empty context"
        )

    # Try to resolve prompt file relative to workflow_dir.
    # For backwards compatibility, check for operation_dir pattern too.
    from darkfactory.engine import ProjectRun

    prompt_path: Path | None = None
    if ctx.state.has(ProjectRun):
        proj = ctx.state.get(ProjectRun)
        wf_dir = proj.workflow.workflow_dir
        if wf_dir is not None:
            candidate = wf_dir / prompt_file
            if candidate.exists():
                prompt_path = candidate

    if prompt_path is None:
        pkg_dir = Path(__file__).resolve().parent.parent / "commands" / "discuss"
        prompt_path = pkg_dir / prompt_file

    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt file not found: {prompt_path}")

    raw_prompt = prompt_path.read_text(encoding="utf-8")
    composed = raw_prompt.replace("{PRD_CONTEXT}", prd_context).replace(
        "{PHASE}", phase
    )

    print_phase_banner(phase)
    time.sleep(1)

    exit_code = spawn_claude(composed, ctx.cwd, effort_level=effort_level)

    if exit_code != 0:
        ctx.logger.warning(
            "discuss_prd: claude exited with code %d during %s phase (continuing)",
            exit_code,
            phase,
        )
