"""Unit tests for the summarize_agent_run built-in."""

from __future__ import annotations

from unittest.mock import MagicMock

from darkfactory.builtins.summarize_agent_run import (
    _format_invocations,
    _format_tool_counts,
    summarize_agent_run,
)


def _make_ctx(*, invoke_count: int = 1, last_invoke_result: object = None) -> MagicMock:
    ctx = MagicMock()
    ctx.invoke_count = invoke_count
    ctx.last_invoke_result = last_invoke_result
    ctx.model = "claude-test"
    ctx.workflow.name = "test-workflow"
    ctx.run_summary = None
    return ctx


# ---------- early return ----------


def test_no_last_invoke_result_returns_early() -> None:
    ctx = _make_ctx(last_invoke_result=None)
    summarize_agent_run(ctx)
    assert ctx.run_summary is None


# ---------- summary generation ----------


def test_successful_run_sets_run_summary() -> None:
    result = MagicMock()
    result.tool_counts = {"Read": 5, "Edit": 3}
    result.sentinel = "PRD_EXECUTE_OK: PRD-999"
    ctx = _make_ctx(invoke_count=2, last_invoke_result=result)

    summarize_agent_run(ctx)

    assert ctx.run_summary is not None
    assert "## Harness execution summary" in ctx.run_summary
    assert "test-workflow" in ctx.run_summary
    assert "claude-test" in ctx.run_summary
    assert "2" in ctx.run_summary
    assert "Edit×3, Read×5" in ctx.run_summary
    assert "PRD_EXECUTE_OK: PRD-999" in ctx.run_summary


def test_run_summary_with_no_tools_shows_none() -> None:
    result = MagicMock()
    result.tool_counts = {}
    result.sentinel = None
    ctx = _make_ctx(invoke_count=1, last_invoke_result=result)

    summarize_agent_run(ctx)

    assert "none" in ctx.run_summary
    assert "**Sentinel:** none" in ctx.run_summary


# ---------- _format_tool_counts ----------


def test_format_tool_counts_empty() -> None:
    assert _format_tool_counts({}) == "none"


def test_format_tool_counts_sorted() -> None:
    assert _format_tool_counts({"Read": 5, "Edit": 3}) == "Edit×3, Read×5"


def test_format_tool_counts_single_entry() -> None:
    assert _format_tool_counts({"Bash": 2}) == "Bash×2"


# ---------- _format_invocations ----------


def test_format_invocations_zero() -> None:
    ctx = _make_ctx(invoke_count=0)
    assert _format_invocations(ctx) == "0"


def test_format_invocations_one() -> None:
    ctx = _make_ctx(invoke_count=1)
    assert _format_invocations(ctx) == "1"


def test_format_invocations_many() -> None:
    ctx = _make_ctx(invoke_count=7)
    assert _format_invocations(ctx) == "7"
