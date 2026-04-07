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

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


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
        return False, f"agent output contained no {success_marker} or {failure_marker} sentinel"

    # Default marker path: use precompiled regexes.
    failure_match = _SENTINEL_FAILURE_RE.search(stdout)
    if failure_match:
        return False, failure_match.group(1).strip()

    success_match = _SENTINEL_SUCCESS_RE.search(stdout)
    if success_match:
        return True, None

    return False, "agent output contained no PRD_EXECUTE_OK or PRD_EXECUTE_FAILED sentinel"


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
) -> InvokeResult:
    """Run Claude Code as a subprocess with the given prompt and return the result.

    The command built is::

        pnpm dlx @anthropic-ai/claude-code --print \\
            --model <model> \\
            --allowed-tools "<comma-joined tools>"

    ``prompt`` is piped to the subprocess via stdin. ``cwd`` sets the
    working directory so relative paths the agent reads/writes resolve
    correctly.

    On timeout, returns a failure result with the reason populated —
    does NOT raise. This matches the runner's expectation that invoke
    returns a structured result no matter what.

    ``dry_run=True`` skips the actual subprocess entirely and returns a
    synthetic success result with empty output. This is what ``prd
    plan`` uses to show what WOULD happen without spending tokens.
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

    cmd: list[str] = [
        executable,
        "dlx",
        "@anthropic-ai/claude-code",
        "--print",
        "--model",
        model,
        "--allowed-tools",
        ",".join(tools),
    ]

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return InvokeResult(
            stdout=exc.stdout or "",  # type: ignore[arg-type]
            stderr=exc.stderr or "",  # type: ignore[arg-type]
            exit_code=-1,
            success=False,
            failure_reason=f"timeout after {timeout_seconds}s",
        )
    except FileNotFoundError:
        return InvokeResult(
            stdout="",
            stderr="",
            exit_code=-1,
            success=False,
            failure_reason=f"executable not found: {executable!r}",
        )

    # Exit code of the CLI itself must be zero for success — but a zero
    # exit code without the sentinel is still a failure (agent didn't
    # report). Parse sentinels regardless of exit code so the reason
    # surface is maximally informative.
    success, failure_reason = _parse_sentinels(
        proc.stdout,
        success_marker=sentinel_success,
        failure_marker=sentinel_failure,
    )

    if proc.returncode != 0 and success:
        # Unusual: sentinel says OK but process exited non-zero. Trust
        # the exit code and surface the real problem.
        success = False
        failure_reason = (
            f"claude exited non-zero ({proc.returncode}) despite success sentinel; "
            f"stderr: {proc.stderr.strip()[:200]}"
        )

    return InvokeResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        success=success,
        failure_reason=failure_reason,
    )
