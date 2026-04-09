"""Built-in: summarize_agent_run — aggregate tool-call counts into a markdown summary."""

from __future__ import annotations

from darkfactory.builtins._registry import builtin
from darkfactory.workflow import ExecutionContext


def _format_tool_counts(tool_counts: dict[str, int]) -> str:
    """Format tool counts as a compact inline string, e.g. 'Edit×3, Read×5'."""
    if not tool_counts:
        return "none"
    return ", ".join(f"{name}×{count}" for name, count in sorted(tool_counts.items()))


def _format_invocations(ctx: ExecutionContext) -> str:
    """Format agent invocation count from context."""
    count = ctx.invoke_count
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    return str(count)


@builtin("summarize_agent_run")
def summarize_agent_run(ctx: ExecutionContext) -> None:
    """Aggregate tool-call counts and write a markdown summary to ctx.run_summary."""
    result = ctx.last_invoke_result
    if result is None:
        return

    lines = [
        "## Harness execution summary",
        "",
        f"- **Workflow:** {ctx.workflow.name}",
        f"- **Model:** {ctx.model or 'unknown'}",
        f"- **Agent invocations:** {_format_invocations(ctx)}",
        f"- **Tools used:** {_format_tool_counts(result.tool_counts)}",
        f"- **Sentinel:** {result.sentinel or 'none'}",
    ]
    ctx.run_summary = "\n".join(lines)
