"""Tests for the Claude Code subprocess wrapper.

The tests mock ``subprocess.run`` so they don't actually invoke Claude
Code — they exercise the wrapper's command-building, sentinel parsing,
timeout handling, and dry-run behavior in isolation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from prd_harness.invoke import (
    CAPABILITY_MODELS,
    InvokeResult,
    _parse_sentinels,
    capability_to_model,
    invoke_claude,
)


# ---------- capability_to_model ----------


def test_capability_to_model_trivial() -> None:
    assert capability_to_model("trivial") == "haiku"


def test_capability_to_model_simple() -> None:
    assert capability_to_model("simple") == "sonnet"


def test_capability_to_model_moderate() -> None:
    assert capability_to_model("moderate") == "sonnet"


def test_capability_to_model_complex() -> None:
    assert capability_to_model("complex") == "opus"


def test_capability_to_model_unknown_falls_back_to_sonnet() -> None:
    """Unknown capabilities shouldn't error — just default to sonnet."""
    assert capability_to_model("foo") == "sonnet"
    assert capability_to_model("") == "sonnet"


def test_capability_models_covers_all_tiers() -> None:
    """Every tier enumerated in the PRD schema should be mapped."""
    assert set(CAPABILITY_MODELS.keys()) == {"trivial", "simple", "moderate", "complex"}


# ---------- _parse_sentinels ----------


def test_parse_sentinels_success() -> None:
    success, reason = _parse_sentinels("some output\nPRD_EXECUTE_OK: PRD-070\n")
    assert success is True
    assert reason is None


def test_parse_sentinels_failure() -> None:
    success, reason = _parse_sentinels(
        "something\nPRD_EXECUTE_FAILED: tests failed\n"
    )
    assert success is False
    assert reason == "tests failed"


def test_parse_sentinels_failure_beats_success() -> None:
    """If both sentinels appear, failure wins (conservative)."""
    stdout = "PRD_EXECUTE_OK: PRD-070\nPRD_EXECUTE_FAILED: actually broken\n"
    success, reason = _parse_sentinels(stdout)
    assert success is False
    assert reason == "actually broken"


def test_parse_sentinels_neither_present() -> None:
    success, reason = _parse_sentinels("just some output, no sentinel\n")
    assert success is False
    assert reason is not None
    assert "sentinel" in reason


def test_parse_sentinels_empty_output() -> None:
    success, reason = _parse_sentinels("")
    assert success is False
    assert reason is not None


def test_parse_sentinels_custom_markers_success() -> None:
    success, reason = _parse_sentinels(
        "output\nMY_OK: done\n",
        success_marker="MY_OK",
        failure_marker="MY_FAIL",
    )
    assert success is True


def test_parse_sentinels_custom_markers_failure() -> None:
    success, reason = _parse_sentinels(
        "output\nMY_FAIL: broke it\n",
        success_marker="MY_OK",
        failure_marker="MY_FAIL",
    )
    assert success is False
    assert reason == "broke it"


def test_parse_sentinels_strips_whitespace_from_reason() -> None:
    success, reason = _parse_sentinels("PRD_EXECUTE_FAILED:   hello world  \n")
    assert reason == "hello world"


# ---------- invoke_claude (dry-run) ----------


def test_invoke_claude_dry_run_returns_synthetic_success(tmp_path: Path) -> None:
    result = invoke_claude(
        prompt="fake prompt",
        tools=["Read", "Edit"],
        model="sonnet",
        cwd=tmp_path,
        dry_run=True,
    )
    assert result.success is True
    assert result.exit_code == 0
    assert "dry-run" in result.stdout
    assert "sonnet" in result.stdout
    assert result.failure_reason is None


def test_invoke_claude_dry_run_does_not_call_subprocess(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        invoke_claude(
            prompt="prompt",
            tools=["Read"],
            model="haiku",
            cwd=tmp_path,
            dry_run=True,
        )
        mock_run.assert_not_called()


# ---------- invoke_claude (mocked subprocess, success path) ----------


def _mock_completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess-shaped mock for patching subprocess.run."""
    return subprocess.CompletedProcess(
        args=["mock"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_invoke_claude_success_sentinel(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(
            stdout="implementation details\nPRD_EXECUTE_OK: PRD-070\n",
            returncode=0,
        )
        result = invoke_claude(
            prompt="p",
            tools=["Read", "Edit"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is True
    assert result.exit_code == 0
    assert result.failure_reason is None
    assert "PRD_EXECUTE_OK" in result.stdout


def test_invoke_claude_builds_expected_command(tmp_path: Path) -> None:
    """The subprocess call should use `pnpm dlx` with the right flags."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(stdout="PRD_EXECUTE_OK: X\n")
        invoke_claude(
            prompt="my prompt",
            tools=["Read", "Edit", "Bash(cargo:*)"],
            model="opus",
            cwd=tmp_path,
        )
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == "pnpm"
        assert cmd[1] == "dlx"
        assert "@anthropic-ai/claude-code" in cmd
        assert "--print" in cmd
        # Model flag
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "opus"
        # Tools flag
        tools_idx = cmd.index("--allowed-tools")
        assert cmd[tools_idx + 1] == "Read,Edit,Bash(cargo:*)"
        # Prompt via stdin
        assert kwargs["input"] == "my prompt"
        # cwd passed through
        assert kwargs["cwd"] == str(tmp_path)


# ---------- invoke_claude (failure path) ----------


def test_invoke_claude_failure_sentinel(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(
            stdout="oh no\nPRD_EXECUTE_FAILED: tests wouldn't pass\n",
            returncode=0,
        )
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is False
    assert result.failure_reason == "tests wouldn't pass"


def test_invoke_claude_nonzero_exit_with_no_sentinel(tmp_path: Path) -> None:
    """Exit code nonzero and no sentinel -> failure with sentinel-missing reason."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(
            stdout="", stderr="agent crashed", returncode=1
        )
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is False
    assert result.exit_code == 1
    assert result.failure_reason is not None


def test_invoke_claude_nonzero_exit_with_success_sentinel(tmp_path: Path) -> None:
    """Exit code nonzero but sentinel says OK -> trust the exit code (failure)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(
            stdout="PRD_EXECUTE_OK: PRD-070\n",
            stderr="something broke after the sentinel",
            returncode=2,
        )
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is False
    assert result.exit_code == 2
    assert result.failure_reason is not None
    assert "non-zero" in result.failure_reason


# ---------- invoke_claude (timeout) ----------


def test_invoke_claude_timeout(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["pnpm"], timeout=5, output="partial output", stderr="partial err"
        )
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
            timeout_seconds=5,
        )
    assert result.success is False
    assert result.exit_code == -1
    assert result.failure_reason is not None
    assert "timeout" in result.failure_reason.lower()
    assert "5" in result.failure_reason


# ---------- invoke_claude (executable missing) ----------


def test_invoke_claude_executable_not_found(tmp_path: Path) -> None:
    """A missing `pnpm` binary should produce a clear error, not crash."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("No such file or directory: 'pnpm'")
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is False
    assert result.failure_reason is not None
    assert "executable not found" in result.failure_reason
