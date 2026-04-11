"""System builtin: gather_prd_context — read target PRD and related PRDs into shared state."""

from __future__ import annotations

from darkfactory.builtins.system_builtins import _register
from darkfactory.prd import PRD
from darkfactory.system import SystemContext


def _one_line_summary(prd: PRD) -> str:
    """First non-empty line of the PRD body, truncated."""
    for line in prd.body.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return prd.title


def _format_prd_ref(prd: PRD) -> str:
    return f"- {prd.id}: {prd.title} (status: {prd.status}) — {_one_line_summary(prd)}"


@_register("gather_prd_context")
def gather_prd_context(ctx: SystemContext) -> None:
    """Read the target PRD file plus parent and dependencies, store context in shared state."""
    if not ctx.target_prd:
        raise ValueError("gather_prd_context requires ctx.target_prd to be set")

    prd = ctx.prds.get(ctx.target_prd)
    if prd is None:
        raise ValueError(f"target PRD {ctx.target_prd!r} not found in loaded PRDs")

    lines: list[str] = []

    lines.append("## Target PRD")
    lines.append(f"- id: {prd.id}")
    lines.append(f"- title: {prd.title}")
    lines.append(f"- status: {prd.status}")
    lines.append(f"- kind: {prd.kind}")
    lines.append("")
    lines.append("### Body")
    lines.append(prd.body)

    if prd.parent:
        lines.append("")
        lines.append("## Parent")
        parent = ctx.prds.get(prd.parent)
        if parent:
            lines.append(_format_prd_ref(parent))
        else:
            lines.append(f"- {prd.parent}: (not found)")

    if prd.depends_on:
        lines.append("")
        lines.append("## Dependencies")
        for dep_id in prd.depends_on:
            dep = ctx.prds.get(dep_id)
            if dep:
                lines.append(_format_prd_ref(dep))
            else:
                lines.append(f"- {dep_id}: (not found)")

    ctx._shared_state["prd_context"] = "\n".join(lines)
    ctx.logger.info("gather_prd_context: collected context for %s", ctx.target_prd)
