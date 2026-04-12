"""Unit tests for shared helpers: _scan_for_forbidden_attribution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from darkfactory.operations._shared import (
    _FORBIDDEN_ATTRIBUTION_PATTERNS,
    _scan_for_forbidden_attribution,
)
from darkfactory.workflow import ExecutionContext


def _run(
    ctx: ExecutionContext,
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command inside ``ctx.cwd`` with dry-run support.

    In dry-run mode, logs the command at INFO level and returns a fake
    ``CompletedProcess`` with exit code 0. In live mode, runs the
    command for real and raises ``subprocess.CalledProcessError`` on
    non-zero exit when ``check=True``.

    Using an explicit argv list (not a shell string) prevents shell
    injection entirely — callers don't get to interpolate variables
    into a command line, they build the argv themselves.
    """
    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return subprocess.run(
        cmd,
        cwd=str(ctx.cwd),
        check=check,
        capture_output=capture,
        text=True,
    )


# ---------- _scan_for_forbidden_attribution ----------


def test_scan_empty_text_is_noop() -> None:
    # Should not raise.
    _scan_for_forbidden_attribution("", source="test")


def test_scan_clean_text_is_noop() -> None:
    _scan_for_forbidden_attribution("chore(prd): PRD-070 start work", source="test")


def test_scan_raises_on_co_authored_by_claude() -> None:
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        _scan_for_forbidden_attribution(
            "Some commit\n\nCo-Authored-By: Claude Sonnet <noreply@anthropic.com>",
            source="commit PRD-070",
        )


def test_scan_raises_on_co_authored_by_anthropic_email() -> None:
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        _scan_for_forbidden_attribution(
            "Some commit\n\nCo-Authored-By: Bot <bot@anthropic.com>",
            source="commit PRD-070",
        )


def test_scan_raises_on_generated_with_claude_code() -> None:
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        _scan_for_forbidden_attribution(
            "Generated with Claude Code",
            source="PR body",
        )


def test_scan_raises_on_robot_emoji_generated_with() -> None:
    with pytest.raises(RuntimeError, match="forbidden attribution"):
        _scan_for_forbidden_attribution(
            "🤖 Generated with something",
            source="PR body",
        )


def test_scan_error_message_includes_source() -> None:
    with pytest.raises(RuntimeError, match="my-source"):
        _scan_for_forbidden_attribution(
            "Co-Authored-By: Claude",
            source="my-source",
        )


def test_forbidden_attribution_patterns_is_tuple() -> None:
    assert isinstance(_FORBIDDEN_ATTRIBUTION_PATTERNS, tuple)
    assert len(_FORBIDDEN_ATTRIBUTION_PATTERNS) > 0


# ---------- _run (dry-run only — no subprocess required) ----------


def test_run_dry_run_returns_zero_returncode(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.dry_run = True
    ctx.cwd = tmp_path

    result = _run(ctx, ["git", "status"])
    assert result.returncode == 0


def test_run_dry_run_returns_empty_stdout(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.dry_run = True
    ctx.cwd = tmp_path

    result = _run(ctx, ["git", "status"])
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_dry_run_logs_command(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.dry_run = True
    ctx.cwd = tmp_path

    _run(ctx, ["git", "status", "--short"])
    ctx.logger.info.assert_called_once()
    call_args = ctx.logger.info.call_args[0]
    assert "git status --short" in call_args[1]
