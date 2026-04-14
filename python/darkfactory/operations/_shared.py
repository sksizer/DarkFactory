from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from darkfactory.workflow import RunContext

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


def _log_dry_run(ctx: "RunContext", message: str) -> bool:
    """Return True (and log) if ``ctx`` is in dry-run mode.

    Eliminates the repeated ``if ctx.dry_run: ctx.logger.info(...); return``
    boilerplate from builtin entry points.  Usage::

        if _log_dry_run(ctx, "git add -A && git commit"):
            return

    The caller may perform additional dry-run-only mutations after the check::

        if _log_dry_run(ctx, "gh pr create ..."):
            ctx.pr_url = "https://example.test/dry-run/pr/0"
            return
    """
    if not ctx.dry_run:
        return False
    ctx.logger.info("[dry-run] %s", message)
    return True


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
