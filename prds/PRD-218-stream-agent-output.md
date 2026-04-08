---
id: "PRD-218"
title: "Stream agent subprocess output in real time"
kind: task
status: in-progress
priority: high
effort: s
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - src/darkfactory/invoke.py
  - src/darkfactory/runner.py
  - tests/test_invoke.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - observability
  - dx
---

# Stream agent subprocess output in real time

## Summary

`invoke_claude` currently runs the Claude Code CLI via `subprocess.run(..., capture_output=True)`, which buffers the entire stdout until the process exits. For a 10-minute agent run, the user sees nothing on their terminal between `✓ [builtin] commit` and the final `✗ timeout after 600s` — no way to tell whether the agent is making progress, stuck in a tool-call loop, or actually thinking.

Replace the buffered subprocess with a streaming one: launch with `Popen`, read stdout line-by-line as the agent writes it, tee each line to the runner's logger AND an in-memory buffer. Sentinel parsing runs against the final buffered output (unchanged semantics). Stderr is captured separately and surfaced on failure.

## Motivation

First live run of PRD-216 hit the 600s timeout with zero intermediate visibility:

```
✓ [builtin] commit
✗ [agent] implement — timeout after 600s
```

No indication of what the agent did in those ten minutes. Did it write any files? Run `just test` twenty times? Loop on a failing mypy error it couldn't fix? We don't know, so we can't tell whether to bump the timeout, fix the workflow, or debug the prompt.

Streaming fixes three problems at once:

1. **Liveness signal** — a scrolling log tells the user the process is alive and roughly what it's doing.
2. **Debuggability** — when a run fails, the stream is the transcript. We don't need to separately fetch the Claude Code log file; the harness already has it.
3. **Early-termination hint** — once a sentinel line appears, we could in principle stop waiting and move on. Out of scope here but enabled by this change.

This also lays the groundwork for **PRD-219 (per-task configurable timeouts)** — without streaming there's no way to tell if a long-running task is healthy.

## Requirements

1. Agent stdout is written to the runner's logger in real time (line-buffered), not buffered until exit.
2. The full stdout is still captured into a buffer so sentinel parsing at the end works exactly as today — success/failure detection semantics are unchanged.
3. Stderr is captured separately and included in `InvokeResult.stderr`.
4. Timeout behavior unchanged: a run that exceeds `timeout_seconds` still raises and returns a failure `InvokeResult`; the partial stdout captured so far is included so the user sees what happened before the kill.
5. The logger line prefix identifies the source (e.g. `agent: ...`) so streamed lines don't get confused with harness log lines.
6. A per-line flush to the terminal — no double-buffering. The user should see each line within ~100ms of the agent writing it.
7. Dry-run path unchanged: no subprocess launched, synthetic success result returned as today.
8. All 26 existing `test_invoke.py` tests continue to pass.

## Technical Approach

### Replace `subprocess.run` with `Popen`

`src/darkfactory/invoke.py`:

```python
import subprocess
import threading
import time
from io import StringIO

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
) -> InvokeResult:
    if dry_run:
        return InvokeResult(...)  # unchanged

    log = logger or logging.getLogger("darkfactory.invoke")
    cmd = [executable, "dlx", "@anthropic-ai/claude-code", "--print",
           "--model", model, "--allowed-tools", ",".join(tools)]

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
        return InvokeResult(..., failure_reason=f"executable not found: {executable!r}")

    # Send the prompt and close stdin so the CLI knows we're done.
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    stdout_buf = StringIO()
    stderr_buf = StringIO()
    deadline = time.monotonic() + timeout_seconds

    # Drain stderr in a background thread so it doesn't deadlock
    # the pipe if Claude writes a lot of warnings.
    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_buf.write(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # Read stdout line-by-line on the main thread, tee to logger + buffer.
    assert proc.stdout is not None
    timed_out = False
    try:
        for line in proc.stdout:
            stdout_buf.write(line)
            log.info("agent: %s", line.rstrip("\n"))
            if time.monotonic() > deadline:
                proc.kill()
                timed_out = True
                break
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stderr_thread.join(timeout=2)

    stdout = stdout_buf.getvalue()
    stderr = stderr_buf.getvalue()
    exit_code = proc.returncode if not timed_out else -1

    if timed_out:
        return InvokeResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=False,
            failure_reason=f"timeout after {timeout_seconds}s",
        )

    success, failure_reason = _parse_sentinels(
        stdout,
        success_marker=sentinel_success,
        failure_marker=sentinel_failure,
    )

    if exit_code != 0 and success:
        success = False
        failure_reason = (
            f"claude exited non-zero ({exit_code}) despite success sentinel; "
            f"stderr: {stderr.strip()[:200]}"
        )

    return InvokeResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        failure_reason=failure_reason,
    )
```

### Timeout handling

The current code uses `subprocess.run(timeout=N)` which blocks the whole call. With streaming we check a wall-clock deadline inside the line-read loop and kill the process if exceeded. This has a tradeoff: a hung agent that writes zero lines won't be killed until the kernel notices and the read unblocks. For the Claude Code CLI, which heartbeats its output, this is fine in practice. If it ever becomes a problem, we can add a `select()` / non-blocking read with a small poll interval — out of scope for this PRD.

### Logger vs stdout

The streamed lines go to `logging` (Python's stdlib logger), which by default writes to stderr. Users see them in their terminal because the harness sets up a handler that writes INFO-level messages to stdout in `cli.py`. Tests that don't care about streaming can use `caplog` to filter them out; tests that do care can assert specific lines.

The log prefix `agent:` makes the source unambiguous. The runner's own log lines (`[builtin] ensure_worktree`) remain visually distinct.

### Partial output on timeout

When the timeout fires, the partial stdout captured so far is included in `InvokeResult.stdout`. The runner's existing error surface just prints `failure_reason`, so the new data isn't immediately visible, but a follow-up PR could print the last N lines of stdout on failure. Out of scope here.

### Tests

New tests in `tests/test_invoke.py`:

1. **`test_invoke_streams_to_logger`** — use `caplog.at_level(logging.INFO, logger="darkfactory.invoke")`, run a tiny fake subprocess (`python -c "import time; print('one'); time.sleep(0.1); print('two')"`), assert both lines appeared in `caplog.records` with the `agent:` prefix.
2. **`test_invoke_captures_full_stdout`** — run the same fake, assert `result.stdout` contains both lines (buffer path still works).
3. **`test_invoke_timeout_returns_partial_stdout`** — fake subprocess that prints a line then sleeps 30s, call with `timeout_seconds=1`, assert result is a timeout failure AND `result.stdout` contains the first line.
4. **`test_invoke_stderr_drained_on_timeout`** — fake subprocess that writes to stderr then blocks; after timeout, `result.stderr` is non-empty.
5. **`test_invoke_sentinel_parsing_unchanged`** — fake subprocess that prints work lines + final sentinel, verify parsing still produces success.

All 5 tests use `executable="python"` with `["-c", ...]` as the argv, not the real Claude Code CLI, so they're fast and offline.

Existing tests should continue to pass. Tests that patched `subprocess.run` will need to be updated to patch `subprocess.Popen` instead — a mechanical change.

## Acceptance Criteria

- [ ] AC-1: Running `prd run PRD-X --execute` shows agent output scrolling in the terminal in real time as the agent writes it (verified manually — no automated test for "human sees scrolling lines").
- [ ] AC-2: `result.stdout` contains the full agent output at end, same as today.
- [ ] AC-3: Sentinel parsing (`_parse_sentinels`) produces identical results as today — the 14 existing sentinel tests all pass unchanged.
- [ ] AC-4: Timeout path includes partial `stdout` captured before the kill.
- [ ] AC-5: Stderr is drained in a background thread so large stderr doesn't deadlock.
- [ ] AC-6: New streaming tests (1–5 above) pass.
- [ ] AC-7: All 26 existing `test_invoke.py` tests pass with the new implementation (possibly with mechanical updates to subprocess mocks).
- [ ] AC-8: Dry-run path unchanged — no subprocess, synthetic success result.
- [ ] AC-9: Log lines carry the `agent:` prefix so they don't blend with harness log lines.

## Open Questions

- [ ] Should streaming go to `print()` directly or through `logging`? `logging` is more configurable (verbosity levels, handlers, file redirection) and matches how the rest of the harness reports progress. Recommendation: `logging`. (Assumed in Technical Approach.)
- [ ] Do we need a `--quiet` flag to suppress the stream? Probably yes eventually, but a Python logger level bump handles it for now (`--verbose` / `-q` already control the root logger). Defer.
- [ ] Do we need `select()` polling to catch hung-but-silent subprocesses faster? Probably not — Claude Code's output cadence is frequent enough that the naive line read works. If it becomes a problem we add polling.
- [ ] Should the streamed transcript be persisted to a file (e.g. `.worktrees/PRD-X/.harness/agent-transcript.log`)? Would be useful for post-mortem debugging. Recommendation: yes, but as a follow-up PRD — not blocking.

## References

- [[PRD-217-process-lock-active-worktrees]] — concurrency hardening thread; this PRD is the observability thread
- PRD-216 first live dogfood run (2026-04-08): 600s timeout with zero visibility surfaced this gap
- [Python subprocess.Popen docs](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
