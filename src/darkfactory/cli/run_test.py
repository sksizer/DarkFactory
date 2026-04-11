"""Tests for cli/run.py — _is_graph_target, argument routing, and run event formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli.run import _is_graph_target, _print_run_event
from darkfactory.graph_execution import RunEvent


# ---------- helpers ----------


def _make_prd(
    *,
    id: str,
    status: str = "ready",
    depends_on: list[str] | None = None,
    parent: str | None = None,
) -> MagicMock:
    prd = MagicMock()
    prd.id = id
    prd.status = status
    prd.depends_on = depends_on or []
    prd.parent = parent
    return prd


def _make_styler() -> MagicMock:
    styler = MagicMock()
    styler.render.side_effect = lambda elem, text: text
    return styler


# ---------- _is_graph_target ----------


def test_is_graph_target_leaf_no_deps_returns_false() -> None:
    """A leaf PRD with no dependencies is a simple single-PRD target."""
    prd = _make_prd(id="PRD-001")
    prds = {"PRD-001": prd}
    with patch("darkfactory.cli.run.containment.is_leaf", return_value=True):
        assert _is_graph_target(prd, prds) is False


def test_is_graph_target_non_leaf_returns_true() -> None:
    """A non-leaf PRD (epic/feature with children) routes through the graph executor."""
    prd = _make_prd(id="PRD-001")
    prds = {"PRD-001": prd}
    with patch("darkfactory.cli.run.containment.is_leaf", return_value=False):
        assert _is_graph_target(prd, prds) is True


def test_is_graph_target_leaf_with_unfinished_dep_returns_true() -> None:
    """A leaf PRD with an unfinished dependency routes through the graph executor."""
    dep = _make_prd(id="PRD-000", status="ready")
    prd = _make_prd(id="PRD-001", depends_on=["PRD-000"])
    prds = {"PRD-000": dep, "PRD-001": prd}
    with patch("darkfactory.cli.run.containment.is_leaf", return_value=True):
        assert _is_graph_target(prd, prds) is True


def test_is_graph_target_leaf_with_done_dep_returns_false() -> None:
    """A leaf PRD whose only dependency is done goes through the single-PRD path."""
    dep = _make_prd(id="PRD-000", status="done")
    prd = _make_prd(id="PRD-001", depends_on=["PRD-000"])
    prds = {"PRD-000": dep, "PRD-001": prd}
    with patch("darkfactory.cli.run.containment.is_leaf", return_value=True):
        assert _is_graph_target(prd, prds) is False


def test_is_graph_target_leaf_with_missing_dep_returns_false() -> None:
    """A leaf PRD whose dependency isn't in the prds dict (unknown) is not a graph target."""
    prd = _make_prd(id="PRD-001", depends_on=["PRD-999"])
    prds = {"PRD-001": prd}
    with patch("darkfactory.cli.run.containment.is_leaf", return_value=True):
        assert _is_graph_target(prd, prds) is False


# ---------- argument routing (cmd_run) ----------


def test_cmd_run_mutual_exclusivity_returns_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--all and a PRD ID are mutually exclusive."""
    import argparse

    from darkfactory.cli.run import cmd_run

    args = argparse.Namespace(
        run_all=True,
        prd_id="PRD-001",
        data_dir=MagicMock(),
        workflows_dir=MagicMock(),
        base=None,
        execute=False,
        json=False,
        model=None,
        workflow=None,
        max_runs=None,
        priority=None,
        tags=None,
        exclude_ids=None,
        timeout=None,
        styler=_make_styler(),
    )
    result = cmd_run(args)
    assert result == 1
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_cmd_run_no_args_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    """cmd_run with no PRD ID and no --all returns 1."""
    import argparse

    from darkfactory.cli.run import cmd_run

    args = argparse.Namespace(
        run_all=False,
        prd_id=None,
        data_dir=MagicMock(),
        workflows_dir=MagicMock(),
        base=None,
        execute=False,
        json=False,
        model=None,
        workflow=None,
        max_runs=None,
        priority=None,
        tags=None,
        exclude_ids=None,
        timeout=None,
        styler=_make_styler(),
    )
    result = cmd_run(args)
    assert result == 1
    err = capsys.readouterr().err
    assert "PRD ID" in err or "--all" in err


# ---------- _print_run_event ----------


def test_print_run_event_start(capsys: pytest.CaptureFixture[str]) -> None:
    """Start events print the PRD ID and optional base ref."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "start"
    ev.prd_id = "PRD-001"
    ev.base_ref = "main"
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "start" in out
    assert "PRD-001" in out
    assert "main" in out


def test_print_run_event_start_no_base(capsys: pytest.CaptureFixture[str]) -> None:
    """Start events without a base ref omit the base annotation."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "start"
    ev.prd_id = "PRD-001"
    ev.base_ref = None
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "base" not in out


def test_print_run_event_finish_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Successful finish events display a success marker."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "finish"
    ev.prd_id = "PRD-001"
    ev.success = True
    ev.pr_url = None
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "✓" in out
    assert "finish" in out
    assert "PRD-001" in out


def test_print_run_event_finish_success_with_pr_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful finish events include the PR URL when present."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "finish"
    ev.prd_id = "PRD-001"
    ev.success = True
    ev.pr_url = "https://github.com/org/repo/pull/42"
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "https://github.com/org/repo/pull/42" in out


def test_print_run_event_finish_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Failed finish events display a failure marker and reason."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "finish"
    ev.prd_id = "PRD-001"
    ev.success = False
    ev.failure_reason = "step failed"
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "✗" in out
    assert "step failed" in out


def test_print_run_event_finish_failure_no_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Failed finish events fall back to 'failed' when no reason is given."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "finish"
    ev.prd_id = "PRD-001"
    ev.success = False
    ev.failure_reason = None
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "failed" in out


def test_print_run_event_skip(capsys: pytest.CaptureFixture[str]) -> None:
    """Skip events print the PRD ID and reason."""
    ev = MagicMock(spec=RunEvent)
    ev.event = "skip"
    ev.prd_id = "PRD-001"
    ev.reason = "already done"
    _print_run_event(ev, _make_styler())
    out = capsys.readouterr().out
    assert "skip" in out
    assert "PRD-001" in out
    assert "already done" in out
