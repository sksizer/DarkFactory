"""Unit tests for analyze_transcript_detectors."""

from __future__ import annotations

from darkfactory.operations.analyze_transcript_detectors import (
    DETECTORS,
    Finding,
    detect_forbidden_attribution_attempt,
    detect_large_thinking_burst,
    detect_repeated_edit,
    detect_retry_count,
    detect_sentinel_failure,
    detect_tool_denied,
    detect_tool_overuse,
    detector,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _assistant(text: str) -> dict[str, object]:
    """Build a minimal assistant event with a single text block."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _assistant_tool_use(name: str, file_path: str) -> dict[str, object]:
    """Build an assistant event with a single tool_use block."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": name,
                    "input": {"file_path": file_path},
                }
            ],
        },
    }


def _assistant_thinking(thinking_text: str) -> dict[str, object]:
    """Build an assistant event with a single thinking block."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking_text}],
        },
    }


def _tool_result(content: str, *, is_error: bool = False) -> dict[str, object]:
    """Build a user event containing a single tool_result."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
    }


def _metadata(task: str) -> dict[str, object]:
    """Build a darkfactory_metadata event."""
    return {
        "type": "darkfactory_metadata",
        "task": task,
        "model": "sonnet",
        "success": True,
        "exit_code": 0,
        "failure_reason": None,
    }


# ---------------------------------------------------------------------------
# sentinel_failure
# ---------------------------------------------------------------------------


def test_detect_sentinel_failure_ok() -> None:
    events = [_assistant("All done.\n\nPRD_EXECUTE_OK: PRD-559.2")]
    findings = detect_sentinel_failure(events)
    assert findings == []


def test_detect_sentinel_failure_explicit_failure() -> None:
    events = [_assistant("PRD_EXECUTE_FAILED: tests did not pass")]
    findings = detect_sentinel_failure(events)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].category == "sentinel_failure"


def test_detect_sentinel_failure_missing_sentinel() -> None:
    events = [_assistant("I finished the work but forgot the sentinel.")]
    findings = detect_sentinel_failure(events)
    assert len(findings) == 1
    assert findings[0].severity == "error"


def test_detect_sentinel_failure_empty_events() -> None:
    assert detect_sentinel_failure([]) == []


def test_detect_sentinel_failure_only_tool_use_no_text() -> None:
    # Last assistant event has no text — counts as missing sentinel
    events = [_assistant_tool_use("Read", "/some/file")]
    findings = detect_sentinel_failure(events)
    assert len(findings) == 1
    assert findings[0].severity == "error"


# ---------------------------------------------------------------------------
# tool_denied
# ---------------------------------------------------------------------------


def test_detect_tool_denied_blocked_event() -> None:
    events = [_tool_result("This command requires approval", is_error=True)]
    findings = detect_tool_denied(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].category == "tool_denied"


def test_detect_tool_denied_security_blocked() -> None:
    events = [
        _tool_result(
            "cd in '/some/path' was blocked. For security, Claude Code may only change directories to allowed working directories.",
            is_error=True,
        )
    ]
    findings = detect_tool_denied(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_detect_tool_denied_regular_error_not_flagged() -> None:
    # A regular command failure (exit code 1) should not be flagged
    events = [_tool_result("Error: No such file or directory: /foo", is_error=True)]
    findings = detect_tool_denied(events)
    assert findings == []


def test_detect_tool_denied_success_not_flagged() -> None:
    events = [_tool_result("file contents here", is_error=False)]
    assert detect_tool_denied(events) == []


def test_detect_tool_denied_multiple() -> None:
    events = [
        _tool_result("This command requires approval", is_error=True),
        _tool_result("This command requires approval", is_error=True),
    ]
    findings = detect_tool_denied(events)
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# retry_count
# ---------------------------------------------------------------------------


def test_detect_retry_count_no_retries() -> None:
    events = [_metadata("implement")]
    assert detect_retry_count(events) == []


def test_detect_retry_count_one_retry_warning() -> None:
    events = [_metadata("implement-retry")]
    findings = detect_retry_count(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].category == "retry_count"


def test_detect_retry_count_three_retries_error() -> None:
    events = [_metadata("implement-retry")] * 3
    findings = detect_retry_count(events)
    assert len(findings) == 1
    assert findings[0].severity == "error"


def test_detect_retry_count_two_retries_warning() -> None:
    events = [_metadata("implement-retry")] * 2
    findings = detect_retry_count(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# repeated_edit
# ---------------------------------------------------------------------------


def test_detect_repeated_edit_no_repeats() -> None:
    events = [
        _assistant_tool_use("Edit", "/a.py"),
        _assistant_tool_use("Edit", "/b.py"),
    ]
    assert detect_repeated_edit(events) == []


def test_detect_repeated_edit_consecutive_same_file() -> None:
    events = [
        _assistant_tool_use("Edit", "/a.py"),
        _assistant_tool_use("Edit", "/a.py"),
    ]
    findings = detect_repeated_edit(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].category == "repeated_edit"
    assert "/a.py" in findings[0].message


def test_detect_repeated_edit_write_consecutive() -> None:
    events = [
        _assistant_tool_use("Write", "/x.py"),
        _assistant_tool_use("Write", "/x.py"),
    ]
    findings = detect_repeated_edit(events)
    assert len(findings) == 1


def test_detect_repeated_edit_non_edit_resets_tracking() -> None:
    # Edit /a.py, then Read (non-edit), then Edit /a.py — no repeat signal
    events = [
        _assistant_tool_use("Edit", "/a.py"),
        _assistant_tool_use("Read", "/b.py"),
        _assistant_tool_use("Edit", "/a.py"),
    ]
    assert detect_repeated_edit(events) == []


def test_detect_repeated_edit_triple_flagged_twice() -> None:
    events = [
        _assistant_tool_use("Edit", "/a.py"),
        _assistant_tool_use("Edit", "/a.py"),
        _assistant_tool_use("Edit", "/a.py"),
    ]
    findings = detect_repeated_edit(events)
    assert len(findings) == 2


def test_repeated_edit_then_write_same_path_flagged() -> None:
    events = [
        _assistant_tool_use("Edit", "config.toml"),
        _assistant_tool_use("Write", "config.toml"),
    ]
    findings = detect_repeated_edit(events)
    assert len(findings) == 1
    assert findings[0].category == "repeated_edit"
    assert "config.toml" in findings[0].message


def test_repeated_write_then_edit_same_path_flagged() -> None:
    events = [
        _assistant_tool_use("Write", "config.toml"),
        _assistant_tool_use("Edit", "config.toml"),
    ]
    findings = detect_repeated_edit(events)
    assert len(findings) == 1
    assert findings[0].category == "repeated_edit"
    assert "config.toml" in findings[0].message


# ---------------------------------------------------------------------------
# large_thinking_burst
# ---------------------------------------------------------------------------


def test_detect_large_thinking_burst_under_threshold() -> None:
    # 100 chars / 4 = 25 estimated tokens — well under 2000
    events = [_assistant_thinking("A" * 100)]
    assert detect_large_thinking_burst(events) == []


def test_detect_large_thinking_burst_over_threshold() -> None:
    # 8001 chars / 4 = 2000 tokens (just at threshold)
    events = [_assistant_thinking("A" * 8001)]
    findings = detect_large_thinking_burst(events)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].category == "large_thinking_burst"


def test_detect_large_thinking_burst_custom_threshold() -> None:
    events = [_assistant_thinking("A" * 400)]
    # threshold=50 → 400//4 = 100 ≥ 50
    findings = detect_large_thinking_burst(events, threshold=50)
    assert len(findings) == 1


def test_detect_large_thinking_burst_no_thinking_blocks() -> None:
    events = [_assistant("just text")]
    assert detect_large_thinking_burst(events) == []


# ---------------------------------------------------------------------------
# forbidden_attribution_attempt
# ---------------------------------------------------------------------------


def test_detect_forbidden_attribution_co_authored_by() -> None:
    events = [_assistant("Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")]
    findings = detect_forbidden_attribution_attempt(events)
    # Matches "Co-Authored-By: Claude" and "@anthropic.com" patterns — at least one
    assert len(findings) >= 1
    assert findings[0].severity == "warning"
    assert findings[0].category == "forbidden_attribution_attempt"


def test_detect_forbidden_attribution_generated_with() -> None:
    events = [_assistant("🤖 Generated with Claude Code")]
    findings = detect_forbidden_attribution_attempt(events)
    assert len(findings) >= 1


def test_detect_forbidden_attribution_generated_with_claude_code() -> None:
    events = [_assistant("Generated with Claude Code")]
    findings = detect_forbidden_attribution_attempt(events)
    assert len(findings) == 1


def test_detect_forbidden_attribution_clean_text() -> None:
    events = [_assistant("I completed the implementation as requested.")]
    assert detect_forbidden_attribution_attempt(events) == []


def test_detect_forbidden_attribution_anthropic_email() -> None:
    events = [_assistant("Co-Authored-By: Someone <someone@anthropic.com>")]
    findings = detect_forbidden_attribution_attempt(events)
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# tool_overuse
# ---------------------------------------------------------------------------


def test_detect_tool_overuse_no_overuse() -> None:
    events = [_assistant_tool_use("Read", f"/file{i}.py") for i in range(10)]
    assert detect_tool_overuse(events) == []


def test_detect_tool_overuse_exceeds_default_threshold() -> None:
    events = [_assistant_tool_use("Read", f"/file{i}.py") for i in range(51)]
    findings = detect_tool_overuse(events)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].category == "tool_overuse"
    assert "Read" in findings[0].message


def test_detect_tool_overuse_exactly_threshold_not_flagged() -> None:
    # exactly 50 — not over
    events = [_assistant_tool_use("Read", f"/file{i}.py") for i in range(50)]
    assert detect_tool_overuse(events) == []


def test_detect_tool_overuse_custom_threshold() -> None:
    events = [_assistant_tool_use("Grep", f"/f{i}.py") for i in range(5)]
    findings = detect_tool_overuse(events, threshold=3)
    assert len(findings) == 1
    assert "Grep" in findings[0].message


def test_detect_tool_overuse_multiple_tools() -> None:
    read_events = [_assistant_tool_use("Read", f"/f{i}.py") for i in range(51)]
    grep_events = [_assistant_tool_use("Grep", f"/g{i}.py") for i in range(51)]
    findings = detect_tool_overuse(read_events + grep_events)
    tool_names = {f.message.split()[0] for f in findings}
    assert "Read" in tool_names
    assert "Grep" in tool_names


# ---------------------------------------------------------------------------
# Custom detector registration (AC-4 from PRD-559.2 / AC-3 from parent PRD-559)
# ---------------------------------------------------------------------------


def test_custom_detector_registration() -> None:
    @detector("test_custom_for_registration")
    def my_detector(events: list[dict[str, object]]) -> list[Finding]:
        return []

    assert "test_custom_for_registration" in DETECTORS
    assert DETECTORS["test_custom_for_registration"] is my_detector


def test_custom_detector_duplicate_raises() -> None:
    import pytest

    @detector("test_dup_once")
    def _first(events: list[dict[str, object]]) -> list[Finding]:
        return []

    with pytest.raises(ValueError, match="Duplicate detector"):

        @detector("test_dup_once")
        def _second(events: list[dict[str, object]]) -> list[Finding]:
            return []
