"""Tests for system_builtins — set_status_bulk, system_load_prds_by_status, system_check_merged."""

from __future__ import annotations

import logging
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from typing import Any

from darkfactory.builtins.system_builtins import (
    SYSTEM_BUILTINS,
    set_status_bulk,
    system_check_merged,
    system_load_prds_by_status,
    system_mark_done,
    system_load_review_prds,
)
from darkfactory.model import PRD, parse_prd
from darkfactory.engine import CandidateList
from darkfactory.system import SystemContext, SystemOperation

from tests.conftest import write_prd


# ---------- helpers ----------


def _make_op() -> SystemOperation:
    return SystemOperation(name="test-op", description="test", tasks=[])


def _make_ctx(
    tmp_path: Path,
    prds: dict[str, PRD] | None = None,
    *,
    dry_run: bool = False,
    targets: list[str] | None = None,
    shared_state: dict[str, object] | None = None,
) -> SystemContext:
    ctx = SystemContext(
        repo_root=tmp_path,
        prds=prds or {},
        operation=_make_op(),
        cwd=tmp_path,
        dry_run=dry_run,
        targets=targets or [],
    )
    if shared_state and "candidates" in shared_state:
        candidates = shared_state["candidates"]
        assert isinstance(candidates, list)
        ctx.state.put(CandidateList(prd_ids=candidates))
    return ctx


def _write_and_parse(tmp_path: Path, prd_id: str, slug: str, **kwargs: Any) -> PRD:
    """Write a PRD fixture to disk and parse it back."""
    write_prd(tmp_path, prd_id, slug, **kwargs)
    return parse_prd(tmp_path / f"{prd_id}-{slug}.md")


# ---------- SYSTEM_BUILTINS registry ----------


def test_all_expected_builtins_registered() -> None:
    expected = {
        "set_status_bulk",
        "system_load_review_prds",
        "system_load_prds_by_status",
        "system_check_merged",
        "system_mark_done",
    }
    assert expected.issubset(set(SYSTEM_BUILTINS.keys()))


def test_builtins_are_callable() -> None:
    for name, fn in SYSTEM_BUILTINS.items():
        assert callable(fn), f"SYSTEM_BUILTINS[{name!r}] is not callable"


# ---------- set_status_bulk — normal writes ----------


def test_set_status_bulk_updates_multiple_prds(tmp_path: Path) -> None:
    prd1 = _write_and_parse(tmp_path, "PRD-1", "alpha", status="review")
    prd2 = _write_and_parse(tmp_path, "PRD-2", "beta", status="review")
    prds = {"PRD-1": prd1, "PRD-2": prd2}
    ctx = _make_ctx(tmp_path, prds, targets=["PRD-1", "PRD-2"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        set_status_bulk(ctx, status="done")

    assert mock_set.call_count == 2
    called_ids = {call_args[0][0].id for call_args in mock_set.call_args_list}
    assert called_ids == {"PRD-1", "PRD-2"}
    called_statuses = {call_args[0][1] for call_args in mock_set.call_args_list}
    assert called_statuses == {"done"}


def test_set_status_bulk_updates_correct_status_value(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-10", "gamma", status="review")
    ctx = _make_ctx(tmp_path, {"PRD-10": prd}, targets=["PRD-10"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        set_status_bulk(ctx, status="done")

    mock_set.assert_called_once_with(prd, "done")


# ---------- set_status_bulk — dry-run ----------


def test_set_status_bulk_dry_run_skips_writes(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-20", "delta", status="review")
    ctx = _make_ctx(tmp_path, {"PRD-20": prd}, dry_run=True, targets=["PRD-20"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        set_status_bulk(ctx, status="done")

    mock_set.assert_not_called()


def test_set_status_bulk_dry_run_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prd = _write_and_parse(tmp_path, "PRD-21", "epsilon", status="review")
    ctx = _make_ctx(tmp_path, {"PRD-21": prd}, dry_run=True, targets=["PRD-21"])

    with caplog.at_level(logging.INFO, logger="darkfactory.system"):
        set_status_bulk(ctx, status="done")

    assert any("dry-run" in rec.message for rec in caplog.records)


# ---------- set_status_bulk — idempotency ----------


def test_set_status_bulk_skips_already_done_prds(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-30", "zeta", status="done")
    ctx = _make_ctx(tmp_path, {"PRD-30": prd}, targets=["PRD-30"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        set_status_bulk(ctx, status="done")

    mock_set.assert_not_called()


def test_set_status_bulk_partial_idempotency(tmp_path: Path) -> None:
    """Only PRDs not already at the target status should be written."""
    prd_done = _write_and_parse(tmp_path, "PRD-31", "eta", status="done")
    prd_review = _write_and_parse(tmp_path, "PRD-32", "theta", status="review")
    prds = {"PRD-31": prd_done, "PRD-32": prd_review}
    ctx = _make_ctx(tmp_path, prds, targets=["PRD-31", "PRD-32"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        set_status_bulk(ctx, status="done")

    # Only PRD-32 should be updated; PRD-31 is already "done"
    mock_set.assert_called_once()
    assert mock_set.call_args[0][0].id == "PRD-32"


def test_set_status_bulk_missing_prd_id_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = _make_ctx(tmp_path, {}, targets=["PRD-999"])

    with caplog.at_level(logging.WARNING, logger="darkfactory.system"):
        set_status_bulk(ctx, status="done")

    assert any("PRD-999" in rec.message for rec in caplog.records)


# ---------- system_load_prds_by_status ----------


def test_system_load_prds_by_status_filters_correctly(tmp_path: Path) -> None:
    prd_review1 = _write_and_parse(tmp_path, "PRD-40", "iota", status="review")
    prd_review2 = _write_and_parse(tmp_path, "PRD-41", "kappa", status="review")
    prd_done = _write_and_parse(tmp_path, "PRD-42", "lambda", status="done")
    prds = {"PRD-40": prd_review1, "PRD-41": prd_review2, "PRD-42": prd_done}
    ctx = _make_ctx(tmp_path, prds)

    system_load_prds_by_status(ctx, status="review")

    assert set(ctx.state.get(CandidateList).prd_ids) == {"PRD-40", "PRD-41"}


def test_system_load_prds_by_status_empty_result(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-50", "mu", status="done")
    ctx = _make_ctx(tmp_path, {"PRD-50": prd})

    system_load_prds_by_status(ctx, status="ready")

    assert ctx.state.get(CandidateList).prd_ids == []


def test_system_load_prds_by_status_stores_in_shared_state(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-51", "nu", status="ready")
    ctx = _make_ctx(tmp_path, {"PRD-51": prd})

    system_load_prds_by_status(ctx, status="ready")

    assert ctx.state.has(CandidateList)
    assert "PRD-51" in ctx.state.get(CandidateList).prd_ids


def test_system_load_review_prds_uses_review_status(tmp_path: Path) -> None:
    prd_review = _write_and_parse(tmp_path, "PRD-52", "xi", status="review")
    prd_ready = _write_and_parse(tmp_path, "PRD-53", "omicron", status="ready")
    prds = {"PRD-52": prd_review, "PRD-53": prd_ready}
    ctx = _make_ctx(tmp_path, prds)

    system_load_review_prds(ctx)

    assert ctx.state.get(CandidateList).prd_ids == ["PRD-52"]


# ---------- system_check_merged — standard merge ----------


def _make_completed(stdout: str = "", returncode: int = 0) -> CompletedProcess:  # type: ignore[type-arg]
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_system_check_merged_standard_merge(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-60", "pi", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-60": prd},
        shared_state={"candidates": ["PRD-60"]},
    )

    def fake_run(cmd: list[str], **kwargs: object) -> CompletedProcess:  # type: ignore[type-arg]
        # local branch --merged check returns a match
        if "--list" in cmd and "-r" not in cmd:
            return _make_completed(stdout="  prd/PRD-60-pi\n")
        return _make_completed(stdout="")

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        system_check_merged(ctx)

    assert "PRD-60" in ctx.targets
    assert any("PRD-60" in line and "standard" in line for line in ctx.report)


def test_system_check_merged_remote_standard_merge(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-61", "rho", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-61": prd},
        shared_state={"candidates": ["PRD-61"]},
    )

    def fake_run(cmd: list[str], **kwargs: object) -> CompletedProcess:  # type: ignore[type-arg]
        # local check returns nothing, remote check returns a match
        if "-r" in cmd and "--list" in cmd:
            return _make_completed(stdout="  origin/prd/PRD-61-rho\n")
        return _make_completed(stdout="")

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        system_check_merged(ctx)

    assert "PRD-61" in ctx.targets


# ---------- system_check_merged — squash-and-merge ----------


def test_system_check_merged_squash_merge(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-70", "sigma", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-70": prd},
        shared_state={"candidates": ["PRD-70"]},
    )

    def fake_run(cmd: list[str], **kwargs: object) -> CompletedProcess:  # type: ignore[type-arg]
        # branch --merged checks return nothing
        if "--merged" in cmd:
            return _make_completed(stdout="")
        # git log --grep finds the branch name in commit history
        if "--grep" in " ".join(cmd) or any("--grep" in arg for arg in cmd):
            return _make_completed(stdout="abc1234 Squash merge prd/PRD-70-sigma\n")
        return _make_completed(stdout="")

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        system_check_merged(ctx)

    assert "PRD-70" in ctx.targets
    assert any("PRD-70" in line and "squash" in line for line in ctx.report)


# ---------- system_check_merged — not merged ----------


def test_system_check_merged_not_merged(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-80", "tau", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-80": prd},
        shared_state={"candidates": ["PRD-80"]},
    )

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=_make_completed(stdout=""),
    ):
        system_check_merged(ctx)

    assert "PRD-80" not in ctx.targets
    assert any("PRD-80" in line and "not merged" in line for line in ctx.report)


def test_system_check_merged_populates_targets_only_with_merged(tmp_path: Path) -> None:
    prd_merged = _write_and_parse(tmp_path, "PRD-81", "upsilon", status="review")
    prd_not = _write_and_parse(tmp_path, "PRD-82", "phi", status="review")
    prds = {"PRD-81": prd_merged, "PRD-82": prd_not}
    ctx = _make_ctx(
        tmp_path,
        prds,
        shared_state={"candidates": ["PRD-81", "PRD-82"]},
    )

    def fake_run(cmd: list[str], **kwargs: object) -> CompletedProcess:  # type: ignore[type-arg]
        # Only PRD-81's branch shows as merged (local branch check)
        if "--merged" in cmd and "prd/PRD-81-upsilon" in " ".join(cmd):
            return _make_completed(stdout="  prd/PRD-81-upsilon\n")
        return _make_completed(stdout="")

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        system_check_merged(ctx)

    assert ctx.targets == ["PRD-81"]


# ---------- system_check_merged — dry-run ----------


def test_system_check_merged_dry_run_no_subprocess(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-90", "chi", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-90": prd},
        dry_run=True,
        shared_state={"candidates": ["PRD-90"]},
    )

    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        system_check_merged(ctx)

    mock_run.assert_not_called()


def test_system_check_merged_dry_run_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prd = _write_and_parse(tmp_path, "PRD-91", "psi", status="review")
    ctx = _make_ctx(
        tmp_path,
        {"PRD-91": prd},
        dry_run=True,
        shared_state={"candidates": ["PRD-91"]},
    )

    with caplog.at_level(logging.INFO, logger="darkfactory.system"):
        system_check_merged(ctx)

    assert any("dry-run" in rec.message for rec in caplog.records)


# ---------- system_check_merged — missing PRD ----------


def test_system_check_merged_missing_prd_skips(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, {}, shared_state={"candidates": ["PRD-999"]})

    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        system_check_merged(ctx)

    mock_run.assert_not_called()
    assert any("PRD-999" in line for line in ctx.report)


# ---------- system_mark_done ----------


def test_system_mark_done_calls_set_status_bulk_with_done(tmp_path: Path) -> None:
    prd = _write_and_parse(tmp_path, "PRD-100", "omega", status="review")
    ctx = _make_ctx(tmp_path, {"PRD-100": prd}, targets=["PRD-100"])

    with patch(
        "darkfactory.builtins.system_builtins.model_module.set_status"
    ) as mock_set:
        system_mark_done(ctx)

    mock_set.assert_called_once_with(prd, "done")
