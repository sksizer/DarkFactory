"""Claude Code subprocess wrapper for AgentTask execution.

The runner doesn't invoke Claude Code directly — it goes through this
module, which builds the subprocess command, pipes the composed prompt
over stdin, captures stdout/stderr, and parses the output for the
sentinel lines that signal success or failure.

Design choices:

- **Subprocess, not SDK**: we shell out to the ``claude`` CLI (via
  ``pnpm dlx @anthropic-ai/claude-code``) rather than importing the
  Anthropic SDK directly. This keeps the harness agnostic to the
  SDK's runtime requirements and lets us target the same CLI that
  humans use interactively, which means prompts tested in chat mostly
  translate cleanly.
- **Sentinel-based success**: the agent is contracted to emit
  ``PRD_EXECUTE_OK: <id>`` or ``PRD_EXECUTE_FAILED: <reason>`` as its
  final line. We parse stdout for these rather than relying on exit
  codes, because the CLI's exit code semantics are coarse and don't
  distinguish "tool refused to run" from "tool ran but the task
  failed".
- **Timeout-bounded**: each invocation has a wall-clock timeout
  (default 10 minutes). Without this, a stuck agent would hang the
  whole harness indefinitely.
- **Capability-to-model mapping**: PRDs declare a ``capability`` field
  (trivial/simple/moderate/complex) that maps to a model. Trivial work
  goes to haiku, complex to opus, everything in between to sonnet.
  Individual AgentTasks can override this explicitly via ``task.model``.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from darkfactory.event_log import EventWriter
    from darkfactory.style import Element, Styler


# ---------- capability -> model mapping ----------


CAPABILITY_MODELS: dict[str, str] = {
    "trivial": "haiku",
    "simple": "sonnet",
    "moderate": "sonnet",
    "complex": "opus",
}
"""PRD capability tier -> Claude model alias.

The runner picks the model for an AgentTask via (in order):

1. Explicit ``task.model`` if set on the AgentTask
2. ``capability_to_model(prd.capability)`` if ``task.model_from_capability=True``
3. Fallback to ``"sonnet"`` if nothing else applies

Overridable from the CLI via ``--model`` on ``prd run``.
"""


def capability_to_model(capability: str) -> str:
    """Return the default model for a PRD capability tier.

    Unknown capabilities fall back to ``sonnet`` rather than raising —
    a PRD with an unrecognized capability should still be runnable,
    just at the default tier.
    """
    return CAPABILITY_MODELS.get(capability, "sonnet")


# ---------- result type ----------


@dataclass
class InvokeResult:
    """Structured outcome of a Claude Code subprocess invocation.

    The runner uses ``success`` to decide whether to continue the
    workflow (True) or mark the PRD blocked (False). ``failure_reason``
    is populated on the failure path so error surfaces can be
    descriptive without having to re-parse the output.
    """

    stdout: str
    stderr: str
    exit_code: int
    success: bool
    failure_reason: str | None = None
    tool_counts: dict[str, int] = field(default_factory=dict)
    sentinel: str | None = None


# ---------- terminal result event ----------


def _find_terminal_result(output_lines: list[str]) -> dict[str, Any] | None:
    """Scan output lines for the last {"type": "result", ...} JSON object."""
    for line in reversed(output_lines):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj: dict[str, Any] = json.loads(line)
            if obj.get("type", "").startswith("darkfactory_"):
                continue
            if obj.get("type") == "result":
                return obj
        except json.JSONDecodeError:
            continue
    return None


# ---------- sentinel parsing ----------


# Anchorless: agents sometimes wrap the sentinel in markdown formatting
# (backticks, blockquote markers, list bullets) when ``claude --print``
# renders their final line. Substring-style matching is more forgiving
# than line-anchored matching and still unambiguous because the marker
# is a fixed token unlikely to appear naturally in PRD work.
_SENTINEL_SUCCESS_RE = re.compile(r"PRD_EXECUTE_OK:\s*(\S[^\n`]*)")
_SENTINEL_FAILURE_RE = re.compile(r"PRD_EXECUTE_FAILED:\s*(\S[^\n`]*)")


def _parse_sentinels(
    stdout: str,
    success_marker: str = "PRD_EXECUTE_OK",
    failure_marker: str = "PRD_EXECUTE_FAILED",
) -> tuple[bool, str | None]:
    """Scan ``stdout`` for sentinel lines and return (success, failure_reason).

    The regex targets the default marker shape. Non-default markers
    passed by the runner (e.g. from an AgentTask that customized them)
    fall through to literal substring matching.

    Precedence: failure beats success. If both sentinels appear in the
    output, we treat it as failure — the agent shouldn't emit both and
    the conservative interpretation is "something went wrong mid-task".
    """
    # Pre-filter: remove darkfactory envelope lines so their JSON values
    # cannot produce false sentinel matches. A darkfactory_stderr line
    # whose "text" field contains a sentinel string (e.g. if the agent's
    # stderr captured a prior sentinel) would otherwise match the regex.
    filtered: list[str] = []
    for raw_line in stdout.splitlines(keepends=True):
        stripped = raw_line.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if parsed.get("type", "").startswith("darkfactory_"):
                    continue
            except json.JSONDecodeError:
                pass
        filtered.append(raw_line)
    stdout = "".join(filtered)

    # Custom marker fast path: if the caller specified non-default markers,
    # fall back to substring matching since we can't know their regex shape.
    if success_marker != "PRD_EXECUTE_OK" or failure_marker != "PRD_EXECUTE_FAILED":
        failure_hit = f"{failure_marker}:" in stdout
        success_hit = f"{success_marker}:" in stdout
        if failure_hit:
            # Best-effort reason extraction: everything after the marker on its line
            for line in stdout.splitlines():
                if line.startswith(f"{failure_marker}:"):
                    reason = line.split(":", 1)[1].strip()
                    return False, reason or "unspecified failure"
            return False, "unspecified failure"
        if success_hit:
            return True, None
        return (
            False,
            f"agent output contained no {success_marker} or {failure_marker} sentinel",
        )

    # Default marker path: use precompiled regexes.
    failure_match = _SENTINEL_FAILURE_RE.search(stdout)
    if failure_match:
        return False, failure_match.group(1).strip()

    success_match = _SENTINEL_SUCCESS_RE.search(stdout)
    if success_match:
        return True, None

    return (
        False,
        "agent output contained no PRD_EXECUTE_OK or PRD_EXECUTE_FAILED sentinel",
    )


# ---------- stream-json event summarization ----------


def _summarize_stream_event(
    event: dict[str, Any],
) -> tuple["Element | None", str, str]:
    """Turn one Claude Code stream-json event into (element, display_text, agent_text).

    Returns:
        element: the semantic :class:`~darkfactory.style.Element` for this
            event, or ``None`` to skip display entirely.
        display_text: a one-line human-readable summary. Empty string when
            ``element`` is ``None``.
        agent_text: the substring that should be appended to the agent-text
            buffer used for sentinel matching. Empty string for non-text
            events. Sentinels can only appear in assistant text, so we
            accumulate text aggressively and let the parser scan it.

    The Claude Code stream-json envelope shapes we care about:

    - ``{"type": "system", "subtype": "init", ...}`` — start of session
    - ``{"type": "assistant", "message": {"content": [...]}}`` — model output
        block (text or tool_use)
    - ``{"type": "user", "message": {"content": [{"type": "tool_result", ...}]}}``
        — tool result echoed back from the harness's perspective
    - ``{"type": "stream_event", "event": {"type": "content_block_delta",
        "delta": {"type": "text_delta", "text": "..."}}}`` — partial message
        chunks (only when --include-partial-messages is set)
    - ``{"type": "result", "subtype": "success"|"error_max_turns"|..., ...}``
        — terminal event with the final message and stats

    Anything not in this list is skipped (element=None).
    """
    from darkfactory.style import Element

    etype = event.get("type")

    if etype == "system":
        subtype = event.get("subtype", "?")
        return (Element.SYSTEM, f"[system] {subtype}", "")

    if etype == "assistant":
        msg = event.get("message", {}) or {}
        content = msg.get("content", []) or []
        # Pick the most informative block. A single assistant event can
        # contain multiple content blocks; we summarize each on its own line
        # by returning only the first here and recursing for the others
        # would over-complicate the contract — instead we join them with
        # ' | '.
        bits: list[str] = []
        text_accum: list[str] = []
        has_tool_use = False
        only_thinking = True
        for block in content:
            btype = block.get("type")
            if btype == "text":
                only_thinking = False
                text = block.get("text") or ""
                text_accum.append(text)
                # Show first 200 chars on a single line; the buffer keeps
                # the full text for sentinel parsing.
                snippet = text.replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                if snippet:
                    bits.append(f"text: {snippet}")
            elif btype == "tool_use":
                only_thinking = False
                has_tool_use = True
                name = block.get("name", "?")
                inp = block.get("input", {}) or {}
                # Render a few high-signal inputs concisely.
                hint = ""
                if isinstance(inp, dict):
                    if "command" in inp:
                        hint = f" {str(inp['command'])[:120]}"
                    elif "file_path" in inp:
                        hint = f" {inp['file_path']}"
                    elif "pattern" in inp:
                        hint = f" /{inp['pattern'][:60]}/"
                    elif "path" in inp:
                        hint = f" {inp['path']}"
                bits.append(f"tool_use: {name}{hint}")
            elif btype == "thinking":
                # Don't echo full thinking — too noisy. Just note it happened.
                bits.append("thinking")
            else:
                only_thinking = False
                bits.append(f"{btype}")

        if not bits:
            return (None, "", "\n".join(text_accum))

        display = " | ".join(bits)
        if has_tool_use:
            element: Element = Element.TOOL_CALL
        elif only_thinking and bits == ["thinking"]:
            element = Element.THINKING
        else:
            element = Element.ASSISTANT_TEXT
        return (element, display, "\n".join(text_accum))

    if etype == "user":
        msg = event.get("message", {}) or {}
        content = msg.get("content", []) or []
        for block in content:
            if block.get("type") == "tool_result":
                raw = block.get("content")
                # tool_result content can be a string or a list of blocks
                if isinstance(raw, list):
                    raw = " ".join(
                        b.get("text", "") for b in raw if isinstance(b, dict)
                    )
                snippet = (raw or "").replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                is_error = block.get("is_error")
                err = " (error)" if is_error else ""
                elem = Element.ERROR if is_error else Element.TOOL_RESULT
                return (elem, f"tool_result{err}: {snippet}", "")
        return (None, "", "")

    if etype == "stream_event":
        ev = event.get("event", {}) or {}
        if ev.get("type") == "content_block_delta":
            delta = ev.get("delta", {}) or {}
            if delta.get("type") == "text_delta":
                text = delta.get("text") or ""
                # Don't log every micro-delta — too noisy. But DO accumulate
                # text into the agent buffer so sentinels build up.
                return (None, "", text)
        return (None, "", "")

    if etype == "rate_limit_event":
        info = event.get("rate_limit_info", {}) or {}
        status = info.get("status", "?")
        util = info.get("utilization")
        rl_type = info.get("rateLimitType", "?")
        util_str = f" {util:.0%}" if isinstance(util, (int, float)) else ""
        return (Element.RATE_LIMIT, f"[rate_limit] {rl_type} {status}{util_str}", "")

    if etype == "result":
        subtype = event.get("subtype", "?")
        msg = event.get("result") or ""
        snippet = str(msg).replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        # Extract token usage if present — render result events bold so the
        # token count stands out (AC-3).
        usage = event.get("usage", {}) or {}
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        total_tokens = input_tokens + output_tokens
        token_str = f" [{total_tokens:,} tokens]" if total_tokens else ""
        display = f"[result] {subtype}{token_str} {snippet}".strip()
        # Use TOKEN_COUNT element when usage info is present so the line
        # renders bold; fall back to SYSTEM otherwise.
        result_elem = Element.TOKEN_COUNT if total_tokens else Element.SYSTEM
        # The result.result field contains the final text, which is where
        # the sentinel typically lands.
        return (result_elem, display, str(msg))

    # Unknown event type — log nothing, accumulate nothing.
    return (None, "", "")


# ---------- main entry point ----------


def invoke_claude(
    prompt: str,
    tools: list[str],
    model: str,
    cwd: Path,
    *,
    sentinel_success: str = "PRD_EXECUTE_OK",
    sentinel_failure: str = "PRD_EXECUTE_FAILED",
    timeout_seconds: int = 600,
    executable: str = "pnpm",
    dry_run: bool = False,
    logger: logging.Logger | None = None,
    styler: "Styler | None" = None,
    _argv_override: list[str] | None = None,
    event_writer: "EventWriter | None" = None,
    event_task_name: str | None = None,
) -> InvokeResult:
    """Run Claude Code as a subprocess with the given prompt and return the result.

    The command built is::

        pnpm dlx @anthropic-ai/claude-code --print \\
            --model <model> \\
            --allowed-tools "<comma-joined tools>"

    ``prompt`` is piped to the subprocess via stdin. ``cwd`` sets the
    working directory so relative paths the agent reads/writes resolve
    correctly.

    Agent stdout is streamed line-by-line to ``logger`` in real time so
    the user can see progress. The full stdout is also captured in a
    buffer so sentinel parsing at the end works as before.

    On timeout, returns a failure result with the reason populated and
    any partial stdout captured before the kill — does NOT raise. This
    matches the runner's expectation that invoke returns a structured
    result no matter what.

    ``dry_run=True`` skips the actual subprocess entirely and returns a
    synthetic success result with empty output. This is what ``prd
    plan`` uses to show what WOULD happen without spending tokens.

    ``_argv_override`` replaces the ``["dlx", "@anthropic-ai/claude-code",
    ...]`` portion of the command with the given list. Intended for
    testing with fake subprocesses (e.g. ``executable="python",
    _argv_override=["-c", "print('hi')"]``).
    """
    if dry_run:
        return InvokeResult(
            stdout=f"[dry-run] would invoke claude with model={model}, "
            f"{len(tools)} tools, prompt={len(prompt)} chars",
            stderr="",
            exit_code=0,
            success=True,
            failure_reason=None,
        )

    log = logger or logging.getLogger("darkfactory.invoke")

    if _argv_override is not None:
        cmd: list[str] = [executable] + list(_argv_override)
    else:
        # --output-format stream-json + --verbose emits JSONL events as
        # they happen (one event per assistant turn, plus tool results,
        # rate-limit warnings, and a final result event) instead of
        # buffering until the process exits. This is what actually makes
        # streaming-to-logger useful — the raw --print mode writes one
        # blob at the very end.
        #
        # We deliberately do NOT pass --include-partial-messages: per-turn
        # granularity is plenty for "is the agent making progress"
        # visibility, and per-delta events add a lot of noise without
        # much extra signal.
        cmd = [
            executable,
            "dlx",
            "@anthropic-ai/claude-code",
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--model",
            model,
            "--allowed-tools",
            ",".join(tools),
            # Prevent the agent from reading/writing outside the project
            # directory (cwd). Without this, file tools accept absolute
            # paths and can escape a worktree into the main repo.
            "--disallowed-tools",
            "Edit(../)",
            "--disallowed-tools",
            "Write(../)",
            "--disallowed-tools",
            "Read(../)",
        ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            text=True,
            bufsize=1,  # line-buffered
        )
    except FileNotFoundError:
        return InvokeResult(
            stdout="",
            stderr="",
            exit_code=-1,
            success=False,
            failure_reason=f"executable not found: {executable!r}",
        )

    # Send the prompt and close stdin so the CLI knows we're done.
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    stdout_buf = StringIO()  # raw stdout (JSONL events when stream-json)
    agent_text_buf = StringIO()  # accumulated assistant text for sentinel matching
    stderr_buf = StringIO()
    tool_counts: dict[str, int] = {}
    deadline = time.monotonic() + timeout_seconds
    process_done = threading.Event()
    timed_out = threading.Event()

    # Drain stderr in a background thread so it doesn't deadlock
    # the pipe if Claude writes a lot of warnings.
    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_buf.write(line)

    # Watchdog thread kills the process if it exceeds the deadline.
    # Uses process_done to wake early when the process finishes normally,
    # keeping mock-based tests fast.
    def _watchdog() -> None:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            process_done.wait(timeout=remaining)
        if not process_done.is_set() and proc.poll() is None:
            proc.kill()
            timed_out.set()

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    stderr_thread.start()
    watchdog_thread.start()

    # Read stdout line-by-line on the main thread. With stream-json each
    # line is a JSON envelope; we summarize each event into a one-line log
    # message and accumulate any assistant text into the sentinel buffer.
    # Lines that fail to parse as JSON (e.g. tests using a plain stub
    # subprocess, or unexpected output) fall back to the legacy behavior
    # of logging the raw line as-is and treating it as agent text.
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            stdout_buf.write(line)
            stripped = line.rstrip("\n")
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                # Not JSON — preserve old behavior. Useful for tests that
                # stub the subprocess with plain text and for diagnostics.
                if styler is not None:
                    from darkfactory.style import Element
                    import sys

                    print(
                        styler.render(Element.ASSISTANT_TEXT, stripped),
                        file=sys.stderr,
                    )
                else:
                    log.info("agent: %s", stripped)
                agent_text_buf.write(stripped + "\n")
                continue

            if not isinstance(event, dict):
                log.info("agent: %s", stripped)
                continue

            # Emit agent_event to the structured event log.
            if event_writer is not None:
                event_writer.emit(
                    "task",
                    "agent_event",
                    task=event_task_name or "agent",
                    event=event,
                )

            element, display_text, agent_text = _summarize_stream_event(event)
            # Accumulate tool-call counts from assistant events.
            if event.get("type") == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        name = block.get("name") or "unknown"
                        tool_counts[name] = tool_counts.get(name, 0) + 1
            if element is not None and display_text:
                if styler is not None:
                    from darkfactory.style import Element
                    import sys

                    # Print with styling to stderr so it doesn't mix with
                    # any stdout output the caller may be collecting.
                    print(styler.render(element, display_text), file=sys.stderr)
                else:
                    log.info("agent: %s", display_text)
            if agent_text:
                # Append verbatim — adding a trailing newline here would
                # break sentinel matching when the marker is split across
                # successive partial-message deltas.
                agent_text_buf.write(agent_text)
    finally:
        # Signal watchdog that the process has exited (or we're cleaning up).
        process_done.set()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stderr_thread.join(timeout=2)
        watchdog_thread.join(timeout=2)

    stdout = stdout_buf.getvalue()
    agent_text = agent_text_buf.getvalue()
    stderr = stderr_buf.getvalue()
    was_timed_out = timed_out.is_set()
    exit_code = -1 if was_timed_out else proc.returncode

    if was_timed_out:
        terminal_result = _find_terminal_result(stdout.splitlines())
        if terminal_result is not None:
            log.warning(
                "Task timed out at %ds but terminal result event found — using result verdict",
                timeout_seconds,
            )
            is_error = terminal_result.get("is_error", True)
            subtype = terminal_result.get("subtype", "")
            result_success = not is_error and subtype != "error"
            return InvokeResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                success=result_success,
                failure_reason=None
                if result_success
                else f"result error (timed out at {timeout_seconds}s): subtype={subtype!r}",
            )
        return InvokeResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=False,
            failure_reason=f"timeout after {timeout_seconds}s",
        )

    # Sentinel parsing scans both the assembled assistant text (the
    # natural place sentinels appear when stream-json is in use) and the
    # raw stdout buffer (covers the legacy text-mode path and tests that
    # stub plain stdout). The two-pass approach is harmless: if neither
    # contains the marker we still produce the same "no sentinel" failure.
    sentinel_haystack = agent_text or stdout
    if (
        agent_text
        and stdout
        and sentinel_success not in agent_text
        and sentinel_failure not in agent_text
    ):
        # Fallback: agent text didn't have it, look in raw stdout too.
        # This catches edge cases where the result event wraps the
        # sentinel differently than the partial-message stream.
        sentinel_haystack = agent_text + "\n" + stdout

    success, failure_reason = _parse_sentinels(
        sentinel_haystack,
        success_marker=sentinel_success,
        failure_marker=sentinel_failure,
    )

    if exit_code != 0 and success:
        # Unusual: sentinel says OK but process exited non-zero. Trust
        # the exit code and surface the real problem.
        success = False
        failure_reason = (
            f"claude exited non-zero ({exit_code}) despite success sentinel; "
            f"stderr: {stderr.strip()[:200]}"
        )

    # Extract the sentinel value (e.g. "PRD-224.3") from the success marker.
    sentinel_value: str | None = None
    if success and sentinel_success == "PRD_EXECUTE_OK":
        m = _SENTINEL_SUCCESS_RE.search(sentinel_haystack)
        if m:
            sentinel_value = m.group(1).strip()

    return InvokeResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        failure_reason=failure_reason,
        tool_counts=tool_counts,
        sentinel=sentinel_value,
    )
