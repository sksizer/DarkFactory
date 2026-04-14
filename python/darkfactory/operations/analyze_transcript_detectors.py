from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar

DetectorFunc = Callable[[list[dict[str, object]]], list["Finding"]]

_F = TypeVar("_F", bound=Callable[..., Any])
"""Signature every detector shares: takes a list of transcript event dicts, returns findings."""

DETECTORS: dict[str, DetectorFunc] = {}
"""Global registry mapping detector name to its implementing function.

Populated via the :func:`detector` decorator. Starts empty at import time;
detectors register themselves when their module is imported.
"""


@dataclass(frozen=True)
class Finding:
    """A single issue or observation produced by a detector."""

    category: str
    severity: Literal["info", "warning", "error"]
    message: str
    line: int | None = None


def detector(name: str) -> Callable[[_F], _F]:
    """Decorator that registers a function in :data:`DETECTORS`.

    Rejects duplicate registrations with ``ValueError`` to catch typos
    and accidental overrides during development.
    """

    def wrapper(func: _F) -> _F:
        if name in DETECTORS:
            raise ValueError(f"Duplicate detector: {name!r}")
        DETECTORS[name] = func
        return func

    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assistant_text(event: dict[str, object]) -> list[str]:
    """Return all text strings from an assistant event's content array."""
    if event.get("type") != "assistant":
        return []
    message = event.get("message", {})
    if not isinstance(message, dict):
        return []
    content = message.get("content", [])
    if not isinstance(content, list):
        return []
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text", "")
            if isinstance(t, str) and t:
                texts.append(t)
    return texts


def _tool_use_items(event: dict[str, object]) -> list[dict[str, object]]:
    """Return all tool_use blocks from an assistant event."""
    if event.get("type") != "assistant":
        return []
    message = event.get("message", {})
    if not isinstance(message, dict):
        return []
    content = message.get("content", [])
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

_DENIAL_KEYWORDS = re.compile(
    r"(requires approval|was blocked|permission denied|not allowed|denied)",
    re.IGNORECASE,
)

_ATTRIBUTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Co-Authored-By:\s*Claude", re.IGNORECASE),
    re.compile(r"Co-Authored-By:.*@anthropic\.com", re.IGNORECASE),
    re.compile(r"Generated with .{0,20}Claude Code", re.IGNORECASE),
    re.compile(r"🤖 Generated with", re.IGNORECASE),
)


@detector("sentinel_failure")
def detect_sentinel_failure(events: list[dict[str, object]]) -> list[Finding]:
    """Check that the final assistant message contains PRD_EXECUTE_OK."""
    assistant_events = [e for e in events if e.get("type") == "assistant"]
    if not assistant_events:
        return []

    last = assistant_events[-1]
    texts = _assistant_text(last)
    full_text = "\n".join(texts)

    if "PRD_EXECUTE_FAILED" in full_text:
        return [
            Finding(
                category="sentinel_failure",
                severity="error",
                message="Final assistant message contains PRD_EXECUTE_FAILED",
            )
        ]
    if "PRD_EXECUTE_OK" not in full_text:
        return [
            Finding(
                category="sentinel_failure",
                severity="error",
                message="Final assistant message lacks PRD_EXECUTE_OK sentinel",
            )
        ]
    return []


@detector("tool_denied")
def detect_tool_denied(events: list[dict[str, object]]) -> list[Finding]:
    """Detect tool calls that were blocked by the harness or permission system."""
    findings = []
    for event in events:
        if event.get("type") != "user":
            continue
        message = event.get("message", {})
        if not isinstance(message, dict):
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            if not block.get("is_error"):
                continue
            error_text = block.get("content", "")
            if not isinstance(error_text, str):
                continue
            if _DENIAL_KEYWORDS.search(error_text):
                findings.append(
                    Finding(
                        category="tool_denied",
                        severity="warning",
                        message=f"Tool call was blocked: {error_text[:120]}",
                    )
                )
    return findings


@detector("retry_count")
def detect_retry_count(events: list[dict[str, object]]) -> list[Finding]:
    """Count harness-driven retries recorded in darkfactory_metadata events."""
    count = sum(
        1
        for e in events
        if isinstance(e, dict)
        and e.get("type") == "darkfactory_metadata"
        and e.get("task") == "implement-retry"
    )
    if count == 0:
        return []
    severity: Literal["info", "warning", "error"] = "error" if count >= 3 else "warning"
    return [
        Finding(
            category="retry_count",
            severity=severity,
            message=f"Harness retried the agent task {count} time(s)",
        )
    ]


@detector("repeated_edit")
def detect_repeated_edit(events: list[dict[str, object]]) -> list[Finding]:
    """Flag consecutive Edit/Write calls to the same file path."""
    findings = []
    prev_key: str | None = None

    for event in events:
        for tool_use in _tool_use_items(event):
            name = tool_use.get("name", "")
            if name not in ("Edit", "Write"):
                prev_key = None
                continue
            inp = tool_use.get("input", {})
            file_path = inp.get("file_path", "") if isinstance(inp, dict) else ""
            key = str(file_path)
            if key == prev_key:
                findings.append(
                    Finding(
                        category="repeated_edit",
                        severity="warning",
                        message=f"Consecutive {name} calls to {file_path}",
                    )
                )
            prev_key = key

    return findings


_THINKING_TOKENS_THRESHOLD = 2000
_CHARS_PER_TOKEN = 4


@detector("large_thinking_burst")
def detect_large_thinking_burst(
    events: list[dict[str, object]],
    threshold: int = _THINKING_TOKENS_THRESHOLD,
) -> list[Finding]:
    """Detect single thinking blocks that exceed the token threshold."""
    findings = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        if not isinstance(message, dict):
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "thinking":
                continue
            thinking_text = block.get("thinking", "")
            if not isinstance(thinking_text, str):
                continue
            estimated_tokens = len(thinking_text) // _CHARS_PER_TOKEN
            if estimated_tokens >= threshold:
                findings.append(
                    Finding(
                        category="large_thinking_burst",
                        severity="info",
                        message=(
                            f"Thinking block estimated at ~{estimated_tokens} tokens "
                            f"(threshold: {threshold})"
                        ),
                    )
                )
    return findings


@detector("forbidden_attribution_attempt")
def detect_forbidden_attribution_attempt(
    events: list[dict[str, object]],
) -> list[Finding]:
    """Detect attribution patterns in assistant messages (advisory)."""
    findings = []
    for event in events:
        for text in _assistant_text(event):
            for pattern in _ATTRIBUTION_PATTERNS:
                match = pattern.search(text)
                if match:
                    findings.append(
                        Finding(
                            category="forbidden_attribution_attempt",
                            severity="warning",
                            message=f"Forbidden attribution pattern found: {match.group(0)!r}",
                        )
                    )
    return findings


_TOOL_OVERUSE_THRESHOLD = 50


@detector("tool_overuse")
def detect_tool_overuse(
    events: list[dict[str, object]],
    threshold: int = _TOOL_OVERUSE_THRESHOLD,
) -> list[Finding]:
    """Detect any tool type used more than the configured threshold."""
    counts: dict[str, int] = {}
    for event in events:
        for tool_use in _tool_use_items(event):
            name = tool_use.get("name", "")
            if isinstance(name, str) and name:
                counts[name] = counts.get(name, 0) + 1

    findings = []
    for tool_name, count in sorted(counts.items()):
        if count > threshold:
            findings.append(
                Finding(
                    category="tool_overuse",
                    severity="warning",
                    message=f"{tool_name} called {count} times (threshold: {threshold})",
                )
            )
    return findings
