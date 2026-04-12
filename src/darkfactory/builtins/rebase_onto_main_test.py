"""Unit tests for rebase_onto_main builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.rebase_onto_main import (
    _fetch_origin_main,
    rebase_onto_main,
)
from darkfactory.utils.git._types import GitErr as _GitErr, Ok as _Ok

_BRANCH = "prd/PRD-001-test-thing"


# ---------- helpers ----------


def _make_ctx(tmp_path: Path, *, event_writer: object = None) -> MagicMock:
    ctx = make_builtin_ctx(tmp_path, event_writer=event_writer)
    ctx.branch_name = _BRANCH
    return ctx


def _ok(stdout: str = "", stderr: str = "") -> CompletedProcess[str]:
    return CompletedProcess([], returncode=0, stdout=stdout, stderr=stderr)


def _fail(
    returncode: int = 1, stdout: str = "", stderr: str = ""
) -> CompletedProcess[str]:
    return CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------- _fetch_origin_main ----------


def test_fetch_main_succeeds_on_zero_exit(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_run:
        mock_run.return_value = _ok()
        _fetch_origin_main(tmp_path, timeout=30)  # should not raise
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["git", "fetch", "origin", "main"]


def test_fetch_main_raises_on_nonzero_exit(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_run:
        mock_run.return_value = _fail(128, stderr="fatal: repository not found")
        with pytest.raises(RuntimeError, match="git fetch origin main failed"):
            _fetch_origin_main(tmp_path, timeout=30)


def test_fetch_main_raises_on_timeout(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            _fetch_origin_main(tmp_path, timeout=30)


# ---------- rebase_onto_main: happy path ----------


def test_rebase_emits_rebased_effect(tmp_path: Path) -> None:
    writer = MagicMock()
    ctx = _make_ctx(tmp_path, event_writer=writer)

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_GitErr(1, "", "", ["git"]),
        ),
        patch(
            "darkfactory.builtins.rebase_onto_main._get_sha",
            side_effect=["old000", "main000", "new000"],
        ),
        patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_sub,
    ):
        mock_sub.return_value = _ok()
        rebase_onto_main(ctx)

    writer.emit.assert_called_once()
    _, kwargs = writer.emit.call_args
    assert kwargs.get("result") == "rebased"
    assert kwargs.get("from_sha") == "old000"
    assert kwargs.get("to_sha") == "new000"
    assert kwargs.get("onto_sha") == "main000"


def test_rebase_calls_git_rebase_origin_main(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_GitErr(1, "", "", ["git"]),
        ),
        patch(
            "darkfactory.builtins.rebase_onto_main._get_sha",
            side_effect=["old000", "main000", "new000"],
        ),
        patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_sub,
    ):
        mock_sub.return_value = _ok()
        rebase_onto_main(ctx)

    mock_sub.assert_called_once()
    args = mock_sub.call_args[0][0]
    assert args == ["git", "rebase", "origin/main"]


# ---------- no-op: already up-to-date ----------


def test_no_op_emits_up_to_date(tmp_path: Path) -> None:
    writer = MagicMock()
    ctx = _make_ctx(tmp_path, event_writer=writer)

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_Ok(None),
        ),
        patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_sub,
    ):
        rebase_onto_main(ctx)

    # rebase should NOT be called
    mock_sub.assert_not_called()
    writer.emit.assert_called_once()
    _, kwargs = writer.emit.call_args
    assert kwargs.get("result") == "up_to_date"


# ---------- conflict: rebase aborted cleanly ----------


def test_conflict_aborts_rebase_and_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    rebase_call = _fail(1, stderr="CONFLICT (content): Merge conflict in foo.py")
    abort_call = _ok()

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_GitErr(1, "", "", ["git"]),
        ),
        patch(
            "darkfactory.builtins.rebase_onto_main._get_sha",
            side_effect=["old000", "main000"],
        ),
        patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_sub,
        patch(
            "darkfactory.builtins.rebase_onto_main._get_conflicting_files",
            return_value=["foo.py", "bar.py"],
        ),
    ):
        mock_sub.side_effect = [rebase_call, abort_call]

        with pytest.raises(RuntimeError, match="conflicts in"):
            rebase_onto_main(ctx)

    # Verify abort was called
    assert mock_sub.call_count == 2
    abort_args = mock_sub.call_args_list[1][0][0]
    assert abort_args == ["git", "rebase", "--abort"]


def test_conflict_error_lists_conflicting_files(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_GitErr(1, "", "", ["git"]),
        ),
        patch(
            "darkfactory.builtins.rebase_onto_main._get_sha",
            side_effect=["old000", "main000"],
        ),
        patch("darkfactory.builtins.rebase_onto_main.subprocess.run") as mock_sub,
        patch(
            "darkfactory.builtins.rebase_onto_main._get_conflicting_files",
            return_value=["src/foo.py", "src/bar.py"],
        ),
    ):
        mock_sub.side_effect = [_fail(1), _ok()]  # rebase fails, abort succeeds

        with pytest.raises(RuntimeError, match="src/foo.py"):
            rebase_onto_main(ctx)


# ---------- fetch main failure ----------


def test_fetch_failure_propagates_runtime_error(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.builtins.rebase_onto_main._fetch_origin_main",
        side_effect=RuntimeError("git fetch origin main failed: network error"),
    ):
        with pytest.raises(RuntimeError, match="network error"):
            rebase_onto_main(ctx)


# ---------- fetch main timeout ----------


def test_fetch_timeout_propagates_runtime_error(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.builtins.rebase_onto_main._fetch_origin_main",
        side_effect=RuntimeError("git fetch origin main timed out after 30s"),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            rebase_onto_main(ctx)


# ---------- event writer is None ----------


def test_none_event_writer_no_emission(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, event_writer=None)

    with (
        patch("darkfactory.builtins.rebase_onto_main._fetch_origin_main"),
        patch(
            "darkfactory.builtins.rebase_onto_main.git_run",
            return_value=_Ok(None),
        ),
    ):
        # Should not raise even with no event writer
        rebase_onto_main(ctx)
