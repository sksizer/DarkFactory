from __future__ import annotations

import re
import subprocess

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


# ----- attribution lint -----
#
# The harness MUST NOT credit Claude / Anthropic in commit messages, PR
# bodies, or run summaries. Default Claude Code commit flows tack on a
# ``Co-Authored-By: Claude ...`` trailer; subagents have been observed to
# do the same inside ``retry_agent`` cycles. We detect and reject those
# patterns loudly rather than silently stripping — silent stripping masks
# the underlying agent misbehaviour we want to notice and fix.
_FORBIDDEN_ATTRIBUTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Co-Authored-By:\s*Claude", re.IGNORECASE),
    re.compile(r"Co-Authored-By:.*@anthropic\.com", re.IGNORECASE),
    re.compile(r"Generated with .{0,20}Claude Code", re.IGNORECASE),
    re.compile(r"🤖 Generated with", re.IGNORECASE),
)


def _scan_for_forbidden_attribution(text: str, *, source: str) -> None:
    """Raise ``RuntimeError`` if ``text`` contains any forbidden pattern.

    ``source`` is a human label (e.g. ``"commit PRD-544"``) included in the
    error so failures point at the offending artifact. No-op on empty text.
    """
    if not text:
        return
    for pattern in _FORBIDDEN_ATTRIBUTION_PATTERNS:
        match = pattern.search(text)
        if match:
            raise RuntimeError(
                f"forbidden attribution pattern in {source}: {match.group(0)!r}. "
                "Claude/Anthropic must never be credited in commit messages, "
                "PR bodies, or run summaries — strip the trailer and retry."
            )
