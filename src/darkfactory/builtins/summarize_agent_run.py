"""Built-in: summarize_agent_run — aggregate tool-call counts into a markdown summary."""

from __future__ import annotations

from darkfactory.builtins._registry import builtin
from darkfactory.engine import AgentResult
from darkfactory.workflow import ExecutionContext


def _format_tool_counts(tool_counts: dict[str, int]) -> str:
    """Format tool counts as a compact inline string, e.g. 'Edit×3, Read×5'."""
    if not tool_counts:
        return "none"
    return ", ".join(f"{name}×{count}" for name, count in sorted(tool_counts.items()))


def _format_invocations(ctx: ExecutionContext) -> str:
    """Format agent invocation count from PhaseState."""
    if not ctx.state.has(AgentResult):
        return "0"
    count = ctx.state.get(AgentResult).invoke_count
    return str(count)


@builtin("summarize_agent_run")
def summarize_agent_run(ctx: ExecutionContext) -> None:
    """Aggregate tool-call counts and write a markdown summary to ctx.run_summary."""
    if not ctx.state.has(AgentResult):
        return

    agent = ctx.state.get(AgentResult)

    lines = [
        "## Harness execution summary",
        "",
        f"- **Workflow:** {ctx.workflow.name}",
        f"- **Model:** {agent.model or 'unknown'}",
        f"- **Agent invocations:** {_format_invocations(ctx)}",
        f"- **Tools used:** {_format_tool_counts(agent.tool_counts)}",
        f"- **Sentinel:** {agent.sentinel or 'none'}",
    ]
    ctx.run_summary = "\n".join(lines)
