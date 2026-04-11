"""Unit tests for fast_forward_branch builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.fast_forward_branch import (
    _check_divergence,
    _fetch_origin_branch,
    fast_forward_branch,
)

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


# ---------- _fetch_origin_branch ----------


def test_fetch_returns_true_on_success(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.return_value = _ok()
        result = _fetch_origin_branch(tmp_path, _BRANCH, timeout=30)
    assert result is True


def test_fetch_returns_false_on_missing_remote_ref(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.return_value = _fail(
            128, stderr="fatal: couldn't find remote ref prd/PRD-001-test-thing"
        )
        result = _fetch_origin_branch(tmp_path, _BRANCH, timeout=30)
    assert result is False


def test_fetch_raises_on_other_failure(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.return_value = _fail(128, stderr="fatal: repository not found")
        with pytest.raises(RuntimeError, match="git fetch origin.*failed"):
            _fetch_origin_branch(tmp_path, _BRANCH, timeout=30)


def test_fetch_raises_on_timeout(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            _fetch_origin_branch(tmp_path, _BRANCH, timeout=30)


# ---------- _check_divergence ----------


def test_check_divergence_returns_none_when_ref_missing(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.return_value = _fail(128)  # rev-parse --verify fails
        result = _check_divergence(tmp_path, _BRANCH)
    assert result is None


def test_check_divergence_returns_counts(tmp_path: Path) -> None:
    with patch("darkfactory.builtins.fast_forward_branch.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _ok("abc123\n"),  # rev-parse --verify
            _ok("0\t3\n"),  # rev-list --left-right --count
        ]
        result = _check_divergence(tmp_path, _BRANCH)
    assert result == (0, 3)


# ---------- fast_forward_branch: happy path (fast-forward) ----------


def test_fast_forward_calls_git_merge(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(0, 3),
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._get_head_sha",
            side_effect=["aaa00001", "bbb00002"],
        ),
        patch("darkfactory.git_ops.subprocess.run") as mock_git,
    ):
        mock_git.return_value = _ok()
        fast_forward_branch(ctx)

    mock_git.assert_called_once()
    call_args = mock_git.call_args[0][0]
    assert call_args == ["git", "merge", "--ff-only", f"origin/{_BRANCH}"]


def test_fast_forward_emits_builtin_effect(tmp_path: Path) -> None:
    writer = MagicMock()
    ctx = _make_ctx(tmp_path, event_writer=writer)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(0, 3),
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._get_head_sha",
            side_effect=["aaa00001", "bbb00002"],
        ),
        patch("darkfactory.git_ops.subprocess.run", return_value=_ok()),
    ):
        fast_forward_branch(ctx)

    writer.emit.assert_called_once()
    _, kwargs = writer.emit.call_args
    assert kwargs.get("result") == "fast_forward"
    assert kwargs.get("from_sha") == "aaa00001"
    assert kwargs.get("to_sha") == "bbb00002"
    assert kwargs.get("commits") == 3


# ---------- no-op: already up-to-date ----------


def test_up_to_date_emits_up_to_date_result(tmp_path: Path) -> None:
    writer = MagicMock()
    ctx = _make_ctx(tmp_path, event_writer=writer)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(0, 0),
        ),
    ):
        fast_forward_branch(ctx)

    writer.emit.assert_called_once()
    _, kwargs = writer.emit.call_args
    assert kwargs.get("result") == "up_to_date"


def test_up_to_date_does_not_call_merge(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(0, 0),
        ),
        patch("darkfactory.git_ops.subprocess.run") as mock_git,
    ):
        fast_forward_branch(ctx)

    mock_git.assert_not_called()


# ---------- remote branch missing ----------


def test_remote_missing_treated_as_up_to_date(tmp_path: Path) -> None:
    writer = MagicMock()
    ctx = _make_ctx(tmp_path, event_writer=writer)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=False,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
        ) as mock_check,
    ):
        fast_forward_branch(ctx)

    mock_check.assert_not_called()
    writer.emit.assert_called_once()
    _, kwargs = writer.emit.call_args
    assert kwargs.get("result") == "up_to_date"


# ---------- local-ahead: fail loudly ----------


def test_local_ahead_raises_with_branch_and_count(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(2, 0),
        ),
    ):
        with pytest.raises(RuntimeError, match=_BRANCH):
            fast_forward_branch(ctx)


def test_local_ahead_error_mentions_ahead_count(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(2, 0),
        ),
    ):
        with pytest.raises(RuntimeError, match="2 commit"):
            fast_forward_branch(ctx)


# ---------- true divergence ----------


def test_diverged_raises_with_both_counts(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(3, 2),
        ),
    ):
        with pytest.raises(RuntimeError, match="diverged"):
            fast_forward_branch(ctx)


# ---------- fetch failure (non-missing-ref) ----------


def test_fetch_failure_propagates_runtime_error(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
        side_effect=RuntimeError("git fetch origin failed: auth error"),
    ):
        with pytest.raises(RuntimeError, match="auth error"):
            fast_forward_branch(ctx)


# ---------- fetch timeout ----------


def test_fetch_timeout_propagates_runtime_error(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
        side_effect=RuntimeError("git fetch origin prd/PRD-001 timed out after 30s"),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            fast_forward_branch(ctx)


# ---------- event writer is None ----------


def test_none_event_writer_no_emission(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, event_writer=None)

    with (
        patch(
            "darkfactory.builtins.fast_forward_branch._fetch_origin_branch",
            return_value=True,
        ),
        patch(
            "darkfactory.builtins.fast_forward_branch._check_divergence",
            return_value=(0, 0),
        ),
    ):
        # Should not raise even with no event writer
        fast_forward_branch(ctx)
