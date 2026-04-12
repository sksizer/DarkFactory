"""Unit tests for the check_rework_guard builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.rework_guard import check_rework_guard, _has_changes
from darkfactory.rework_guard import ReworkGuard


# ---------- _has_changes helper ----------


def test_has_changes_returns_true_when_output(tmp_path: Path) -> None:
    result = subprocess.CompletedProcess([], returncode=0, stdout=" M some_file.py\n", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=result):
        assert _has_changes(str(tmp_path)) is True


def test_has_changes_returns_false_when_empty(tmp_path: Path) -> None:
    result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=result):
        assert _has_changes(str(tmp_path)) is False


# ---------- dry-run mode ----------


def test_dry_run_logs_and_does_not_touch_state(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        check_rework_guard(ctx)
    mock_run.assert_not_called()
    ctx.logger.info.assert_called()
    # State file should not exist.
    assert not (tmp_path / ".darkfactory" / "state" / "rework-guard.json").exists()


# ---------- changes present ----------


def test_with_changes_resets_counter(tmp_path: Path) -> None:
    # Seed the guard with a no-change entry.
    guard = ReworkGuard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)

    ctx = make_builtin_ctx(tmp_path)
    status_result = subprocess.CompletedProcess([], returncode=0, stdout=" M file.py\n", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)  # should not raise

    fresh_guard = ReworkGuard(tmp_path)
    assert fresh_guard.get_consecutive_no_change("PRD-001") == 0


def test_with_changes_logs_info(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    status_result = subprocess.CompletedProcess([], returncode=0, stdout=" M file.py\n", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)
    ctx.logger.info.assert_called()


# ---------- no changes — below threshold ----------


def test_no_changes_below_threshold_does_not_raise(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    status_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)  # should not raise — first no-change (below N=2)


def test_no_changes_increments_counter(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    status_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)

    guard = ReworkGuard(tmp_path)
    assert guard.get_consecutive_no_change("PRD-001") == 1


# ---------- no changes — at threshold (blocked) ----------


def test_no_changes_at_threshold_raises(tmp_path: Path) -> None:
    # Seed one no-change so the next one hits the default threshold of 2.
    guard = ReworkGuard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)

    ctx = make_builtin_ctx(tmp_path)
    status_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        with pytest.raises(RuntimeError, match="REWORK LOOP BLOCKED"):
            check_rework_guard(ctx)


def test_blocked_error_message_contains_prd_id(tmp_path: Path) -> None:
    guard = ReworkGuard(tmp_path)
    guard.record_outcome("PRD-042", had_changes=False)

    ctx = make_builtin_ctx(tmp_path, prd_id="PRD-042")
    status_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        with pytest.raises(RuntimeError, match="PRD-042"):
            check_rework_guard(ctx)


# ---------- event writer integration ----------


def test_event_writer_called_with_changes(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.event_writer = MagicMock()
    status_result = subprocess.CompletedProcess([], returncode=0, stdout=" M file.py\n", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)
    ctx.event_writer.emit.assert_called_once()
    call_kwargs = ctx.event_writer.emit.call_args
    assert call_kwargs[0][1] == "rework_guard"
    assert call_kwargs[1]["had_changes"] is True


def test_event_writer_called_without_changes(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.event_writer = MagicMock()
    status_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch("darkfactory.utils.git._run.subprocess.run", return_value=status_result):
        check_rework_guard(ctx)
    ctx.event_writer.emit.assert_called_once()
    call_kwargs = ctx.event_writer.emit.call_args
    assert call_kwargs[1]["had_changes"] is False
