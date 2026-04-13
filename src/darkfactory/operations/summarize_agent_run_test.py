"""Unit tests for the summarize_agent_run built-in."""

from __future__ import annotations

from pathlib import Path

from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.summarize_agent_run import (
    _format_invocations,
    _format_tool_counts,
    summarize_agent_run,
)
from darkfactory.engine import AgentResult, PrdWorkflowRun
from darkfactory.workflow import RunContext, Workflow


def _make_ctx(tmp_path: Path, *, agent_result: AgentResult | None = None) -> RunContext:
    ctx = make_builtin_ctx(tmp_path)
    # Override workflow name to match test expectations
    prd_run = ctx.state.get(PrdWorkflowRun)
    ctx.state.put(
        PrdWorkflowRun(
            prd=prd_run.prd,
            workflow=Workflow(name="test-workflow", tasks=[]),
        )
    )
    if agent_result is not None:
        ctx.state.put(agent_result)
    return ctx


# ---------- early return ----------


def test_no_last_invoke_result_returns_early(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    summarize_agent_run(ctx)
    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.run_summary is None


# ---------- summary generation ----------


def test_successful_run_sets_run_summary(tmp_path: Path) -> None:
    result = AgentResult(
        stdout="",
        stderr="",
        exit_code=0,
        success=True,
        tool_counts={"Read": 5, "Edit": 3},
        sentinel="PRD_EXECUTE_OK: PRD-999",
        model="claude-test",
        invoke_count=2,
    )
    ctx = _make_ctx(tmp_path, agent_result=result)

    summarize_agent_run(ctx)

    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.run_summary is not None
    assert "## Harness execution summary" in prd_run.run_summary
    assert "test-workflow" in prd_run.run_summary
    assert "claude-test" in prd_run.run_summary
    assert "2" in prd_run.run_summary
    assert "Edit×3, Read×5" in prd_run.run_summary
    assert "PRD_EXECUTE_OK: PRD-999" in prd_run.run_summary


def test_run_summary_with_no_tools_shows_none(tmp_path: Path) -> None:
    result = AgentResult(
        stdout="",
        stderr="",
        exit_code=0,
        success=True,
        tool_counts={},
        sentinel=None,
        model="claude-test",
        invoke_count=1,
    )
    ctx = _make_ctx(tmp_path, agent_result=result)

    summarize_agent_run(ctx)

    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.run_summary is not None
    assert "none" in prd_run.run_summary
    assert "**Sentinel:** none" in prd_run.run_summary


# ---------- _format_tool_counts ----------


def test_format_tool_counts_empty() -> None:
    assert _format_tool_counts({}) == "none"


def test_format_tool_counts_sorted() -> None:
    assert _format_tool_counts({"Read": 5, "Edit": 3}) == "Edit×3, Read×5"


def test_format_tool_counts_single_entry() -> None:
    assert _format_tool_counts({"Bash": 2}) == "Bash×2"


# ---------- _format_invocations ----------


def test_format_invocations_zero(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert _format_invocations(ctx) == "0"


def test_format_invocations_one(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path,
        agent_result=AgentResult(
            stdout="",
            stderr="",
            exit_code=0,
            success=True,
            invoke_count=1,
        ),
    )
    assert _format_invocations(ctx) == "1"


def test_format_invocations_many(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path,
        agent_result=AgentResult(
            stdout="",
            stderr="",
            exit_code=0,
            success=True,
            invoke_count=7,
        ),
    )
    assert _format_invocations(ctx) == "7"
