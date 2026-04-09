"""Tests for the Claude Code subprocess wrapper.

Existing tests that previously patched ``subprocess.run`` have been updated
to patch ``subprocess.Popen`` to match the streaming implementation.  Five
new tests (marked with ``# NEW``) cover the streaming-specific behaviour:
logger tee, full-stdout capture, partial stdout on timeout, stderr drain,
and unchanged sentinel parsing.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


from darkfactory.invoke import (
    CAPABILITY_MODELS,
    _find_terminal_result,
    _parse_sentinels,
    capability_to_model,
    invoke_claude,
)


# ---------- helpers ----------


def _make_mock_popen(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> MagicMock:
    """Build a mock Popen object for patching ``subprocess.Popen``.

    ``proc.stdout`` and ``proc.stderr`` are ``io.StringIO`` instances so the
    line-reading loops in ``invoke_claude`` work without spawning a real
    process.  ``proc.poll()`` returns ``returncode`` immediately so the
    watchdog thread knows the process is already done and exits without
    sleeping through the full timeout.
    """
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = io.StringIO(stdout)
    mock_proc.stderr = io.StringIO(stderr)
    mock_proc.returncode = returncode
    mock_proc.wait.return_value = returncode
    mock_proc.poll.return_value = returncode  # process already exited
    return mock_proc


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
    success, reason = _parse_sentinels("something\nPRD_EXECUTE_FAILED: tests failed\n")
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


def test_parse_sentinels_success_in_inline_code() -> None:
    """Agents sometimes wrap the sentinel in markdown backticks when
    ``claude --print`` renders their final line. The parser should
    still recognize it."""
    success, reason = _parse_sentinels("verifying ACs...\n`PRD_EXECUTE_OK: PRD-501`\n")
    assert success is True
    assert reason is None


def test_parse_sentinels_failure_in_inline_code() -> None:
    success, reason = _parse_sentinels("`PRD_EXECUTE_FAILED: missing dep`\n")
    assert success is False
    assert reason == "missing dep"


def test_parse_sentinels_success_in_blockquote() -> None:
    success, reason = _parse_sentinels("> PRD_EXECUTE_OK: PRD-501\n")
    assert success is True


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
    with patch("subprocess.Popen") as mock_popen:
        invoke_claude(
            prompt="prompt",
            tools=["Read"],
            model="haiku",
            cwd=tmp_path,
            dry_run=True,
        )
        mock_popen.assert_not_called()


# ---------- invoke_claude (mocked subprocess, success path) ----------


def test_invoke_claude_success_sentinel(tmp_path: Path) -> None:
    mock_proc = _make_mock_popen(
        stdout="implementation details\nPRD_EXECUTE_OK: PRD-070\n",
        returncode=0,
    )
    with patch("subprocess.Popen", return_value=mock_proc):
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
    mock_proc = _make_mock_popen(stdout="PRD_EXECUTE_OK: X\n")
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        invoke_claude(
            prompt="my prompt",
            tools=["Read", "Edit", "Bash(cargo:*)"],
            model="opus",
            cwd=tmp_path,
        )
        args, kwargs = mock_popen.call_args
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
        # Prompt written to stdin (not passed as input= kwarg)
        mock_proc.stdin.write.assert_called_once_with("my prompt")
        # cwd passed through
        assert kwargs["cwd"] == str(tmp_path)


# ---------- invoke_claude (failure path) ----------


def test_invoke_claude_failure_sentinel(tmp_path: Path) -> None:
    mock_proc = _make_mock_popen(
        stdout="oh no\nPRD_EXECUTE_FAILED: tests wouldn't pass\n",
        returncode=0,
    )
    with patch("subprocess.Popen", return_value=mock_proc):
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
    mock_proc = _make_mock_popen(stdout="", stderr="agent crashed", returncode=1)
    with patch("subprocess.Popen", return_value=mock_proc):
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
    mock_proc = _make_mock_popen(
        stdout="PRD_EXECUTE_OK: PRD-070\n",
        stderr="something broke after the sentinel",
        returncode=2,
    )
    with patch("subprocess.Popen", return_value=mock_proc):
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
    """Timeout path: success=False, exit_code=-1, failure_reason contains 'timeout'.

    Uses a real Python subprocess that sleeps 30s so the watchdog fires
    after timeout_seconds=1 and kills it.  Takes ~1s to run.
    """
    result = invoke_claude(
        prompt="p",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=["-c", "import time; time.sleep(30)"],
        timeout_seconds=1,
    )
    assert result.success is False
    assert result.exit_code == -1
    assert result.failure_reason is not None
    assert "timeout" in result.failure_reason.lower()
    assert "1" in result.failure_reason


# ---------- invoke_claude (executable missing) ----------


def test_invoke_claude_executable_not_found(tmp_path: Path) -> None:
    """A missing `pnpm` binary should produce a clear error, not crash."""
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = FileNotFoundError("No such file or directory: 'pnpm'")
        result = invoke_claude(
            prompt="p",
            tools=["Read"],
            model="sonnet",
            cwd=tmp_path,
        )
    assert result.success is False
    assert result.failure_reason is not None
    assert "executable not found" in result.failure_reason


# ---------- NEW: streaming tests ----------


def test_invoke_streams_to_logger(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:  # NEW
    """Each stdout line is logged to 'darkfactory.invoke' at INFO level with 'agent:' prefix."""
    with caplog.at_level(logging.INFO, logger="darkfactory.invoke"):
        invoke_claude(
            prompt="irrelevant",
            tools=[],
            model="sonnet",
            cwd=tmp_path,
            executable="python",
            _argv_override=[
                "-c",
                "import time; print('one', flush=True); time.sleep(0.05); print('two', flush=True)",
            ],
        )

    messages = [r.getMessage() for r in caplog.records]
    assert any(m == "agent: one" for m in messages)
    assert any(m == "agent: two" for m in messages)


def test_invoke_captures_full_stdout(tmp_path: Path) -> None:  # NEW
    """result.stdout contains the complete agent output even with streaming."""
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=[
            "-c",
            "import time; print('one', flush=True); time.sleep(0.05); print('two', flush=True)",
        ],
    )
    assert "one" in result.stdout
    assert "two" in result.stdout


def test_invoke_timeout_returns_partial_stdout(tmp_path: Path) -> None:  # NEW
    """Partial stdout captured before timeout kill is included in result.stdout.

    Takes ~1s to run (real subprocess that sleeps 30s, killed after 1s).
    """
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=[
            "-c",
            "print('partial', flush=True); import time; time.sleep(30)",
        ],
        timeout_seconds=1,
    )
    assert result.success is False
    assert "timeout" in result.failure_reason.lower()  # type: ignore[union-attr]
    assert "partial" in result.stdout


def test_invoke_stderr_drained_on_timeout(tmp_path: Path) -> None:  # NEW
    """Stderr written before timeout is included in result.stderr.

    Takes ~1s to run (real subprocess that writes stderr then sleeps 30s).
    """
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=[
            "-c",
            (
                "import sys; "
                "sys.stderr.write('err output\\n'); "
                "sys.stderr.flush(); "
                "import time; time.sleep(30)"
            ),
        ],
        timeout_seconds=1,
    )
    assert result.success is False
    assert result.stderr  # non-empty


def test_invoke_sentinel_parsing_unchanged(tmp_path: Path) -> None:  # NEW
    """Sentinel parsing produces identical results with the streaming implementation."""
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=[
            "-c",
            "print('doing work'); print('PRD_EXECUTE_OK: PRD-218')",
        ],
    )
    assert result.success is True
    assert result.failure_reason is None
    assert "PRD_EXECUTE_OK" in result.stdout


# ---------- stream-json event parsing ----------


def test_invoke_parses_stream_json_assistant_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each stream-json assistant event with text content is summarized to
    the logger and accumulates into the agent text buffer used for sentinel
    matching."""
    events = [
        '{"type":"system","subtype":"init"}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"reading files"}]}}',
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"src/foo.py"}}]}}',
        '{"type":"user","message":{"content":[{"type":"tool_result","content":"file content"}]}}',
        '{"type":"result","subtype":"success","result":"PRD_EXECUTE_OK: PRD-T"}',
    ]
    script = "\n".join(f"print({e!r})" for e in events)
    with caplog.at_level(logging.INFO, logger="darkfactory.invoke"):
        result = invoke_claude(
            prompt="irrelevant",
            tools=[],
            model="sonnet",
            cwd=tmp_path,
            executable="python",
            _argv_override=["-c", script],
        )
    assert result.success is True, result.failure_reason
    messages = [r.getMessage() for r in caplog.records]
    assert any("[system] init" in m for m in messages)
    assert any("text: reading files" in m for m in messages)
    assert any("tool_use: Read src/foo.py" in m for m in messages)
    assert any("tool_result" in m for m in messages)
    assert any("[result] success" in m for m in messages)


def test_invoke_parses_stream_json_partial_text_deltas(
    tmp_path: Path,
) -> None:
    """Partial-message stream_event deltas accumulate into the agent text
    buffer so a sentinel split across deltas is still recognized."""
    events = [
        '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"PRD_EXEC"}}}',
        '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"UTE_OK: PRD-T"}}}',
    ]
    script = "\n".join(f"print({e!r})" for e in events)
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=["-c", script],
    )
    assert result.success is True, result.failure_reason


def test_invoke_unknown_event_types_are_ignored(tmp_path: Path) -> None:
    """An unrecognized event type doesn't crash and doesn't break the run."""
    events = [
        '{"type":"some_future_event","payload":"???"}',
        '{"type":"result","subtype":"success","result":"PRD_EXECUTE_OK: PRD-T"}',
    ]
    script = "\n".join(f"print({e!r})" for e in events)
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=["-c", script],
    )
    assert result.success is True, result.failure_reason


def test_invoke_parses_rate_limit_event(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Rate limit warnings surface as a [rate_limit] log line so the user
    sees them in real time."""
    events = [
        '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed_warning","rateLimitType":"seven_day","utilization":0.94}}',
        '{"type":"result","subtype":"success","result":"PRD_EXECUTE_OK: PRD-T"}',
    ]
    script = "\n".join(f"print({e!r})" for e in events)
    with caplog.at_level(logging.INFO, logger="darkfactory.invoke"):
        result = invoke_claude(
            prompt="irrelevant",
            tools=[],
            model="sonnet",
            cwd=tmp_path,
            executable="python",
            _argv_override=["-c", script],
        )
    assert result.success is True
    messages = [r.getMessage() for r in caplog.records]
    assert any("[rate_limit] seven_day allowed_warning 94%" in m for m in messages)


def test_invoke_parses_assistant_with_thinking_and_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A single assistant event can carry both a thinking block and a text
    block (this is the shape Claude Code emits in --verbose stream-json
    mode). Both should surface in the log line."""
    event = (
        '{"type":"assistant","message":{"content":['
        '{"type":"thinking","thinking":"hmm let me think"},'
        '{"type":"text","text":"the answer is 42"}'
        "]}}"
    )
    final = '{"type":"result","subtype":"success","result":"PRD_EXECUTE_OK: PRD-T"}'
    script = f"print({event!r})\nprint({final!r})"
    with caplog.at_level(logging.INFO, logger="darkfactory.invoke"):
        result = invoke_claude(
            prompt="irrelevant",
            tools=[],
            model="sonnet",
            cwd=tmp_path,
            executable="python",
            _argv_override=["-c", script],
        )
    assert result.success is True
    messages = [r.getMessage() for r in caplog.records]
    # Both thinking and text appear in the same log line, joined with " | "
    assert any("thinking" in m and "text: the answer is 42" in m for m in messages)


def test_invoke_invalid_json_falls_back_to_plain_text(tmp_path: Path) -> None:
    """A line that isn't valid JSON is logged as-is and treated as agent
    text. This is the legacy --print plain-text mode and the test-stub
    path that the existing tests above all rely on."""
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=[
            "-c",
            "print('not json'); print('PRD_EXECUTE_OK: PRD-T')",
        ],
    )
    assert result.success is True
    assert "not json" in result.stdout


# ---------- _find_terminal_result ----------


def test_find_terminal_result_no_result_line() -> None:
    lines = ["some output", "no json here", '{"type":"assistant","text":"hi"}']
    assert _find_terminal_result(lines) is None


def test_find_terminal_result_present() -> None:
    lines = [
        "some output",
        '{"type":"result","subtype":"success","is_error":false}',
    ]
    result = _find_terminal_result(lines)
    assert result is not None
    assert result["type"] == "result"
    assert result["subtype"] == "success"


def test_find_terminal_result_multiple_json_picks_result() -> None:
    lines = [
        '{"type":"assistant","message":"hello"}',
        '{"type":"result","subtype":"success","is_error":false}',
        '{"type":"system","subtype":"init"}',
    ]
    result = _find_terminal_result(lines)
    assert result is not None
    assert result["type"] == "result"


def test_find_terminal_result_malformed_json_skipped() -> None:
    lines = [
        "{bad json}",
        '{"type":"result","subtype":"success","is_error":false}',
    ]
    result = _find_terminal_result(lines)
    assert result is not None
    assert result["type"] == "result"


def test_find_terminal_result_only_malformed_json() -> None:
    lines = ["{bad json}", "{also bad"]
    assert _find_terminal_result(lines) is None


def test_find_terminal_result_picks_last_result() -> None:
    lines = [
        '{"type":"result","subtype":"error","is_error":true}',
        '{"type":"result","subtype":"success","is_error":false}',
    ]
    # reversed scan picks the last one (success)
    result = _find_terminal_result(lines)
    assert result is not None
    assert result["subtype"] == "success"


# ---------- timeout with terminal result event ----------


def test_invoke_timeout_with_result_event_uses_result_verdict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When a task times out but already emitted a result event, the outcome
    is based on the result event (not timeout failure).

    Takes ~1s (real subprocess killed after 1s).
    """
    result_event = '{"type":"result","subtype":"success","is_error":false,"result":"PRD_EXECUTE_OK: PRD-T"}'
    script = f"print({result_event!r}, flush=True); import time; time.sleep(30)"
    with caplog.at_level(logging.WARNING, logger="darkfactory.invoke"):
        result = invoke_claude(
            prompt="irrelevant",
            tools=[],
            model="sonnet",
            cwd=tmp_path,
            executable="python",
            _argv_override=["-c", script],
            timeout_seconds=1,
        )
    assert result.success is True
    assert result.exit_code == -1  # was killed
    messages = [r.getMessage() for r in caplog.records]
    assert any("terminal result event found" in m for m in messages)


def test_invoke_timeout_with_error_result_event_uses_error_verdict(
    tmp_path: Path,
) -> None:
    """When result event has is_error=True, timeout path reports failure from event."""
    result_event = '{"type":"result","subtype":"error","is_error":true}'
    script = f"print({result_event!r}, flush=True); import time; time.sleep(30)"
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=["-c", script],
        timeout_seconds=1,
    )
    assert result.success is False
    assert result.exit_code == -1
    # failure_reason should NOT say "timeout after" — it comes from the result event
    assert result.failure_reason is not None
    assert "timeout after" not in result.failure_reason


def test_invoke_timeout_without_result_event_is_timeout_failure(
    tmp_path: Path,
) -> None:
    """When no result event is emitted before timeout, behavior is unchanged:
    failure with 'timeout' in failure_reason.

    Takes ~1s (real subprocess killed after 1s).
    """
    result = invoke_claude(
        prompt="irrelevant",
        tools=[],
        model="sonnet",
        cwd=tmp_path,
        executable="python",
        _argv_override=["-c", "import time; time.sleep(30)"],
        timeout_seconds=1,
    )
    assert result.success is False
    assert result.exit_code == -1
    assert result.failure_reason is not None
    assert "timeout" in result.failure_reason.lower()
