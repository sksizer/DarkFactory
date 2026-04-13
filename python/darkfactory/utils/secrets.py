"""Secrets filtering for DarkFactory output.

Scans text content for common credential and secret patterns before it
is committed, posted to PRs, or otherwise made visible. Intended to be
called as a pre-commit filter on transcripts, analysis files, and PR
bodies.

This is a best-effort filter — it catches common patterns but cannot
guarantee detection of all sensitive content. Defense in depth (gitignored
transcripts, opt-in commit config) remains the primary protection.

Usage::

    from darkfactory.utils.secrets import redact

    safe_text = redact(potentially_sensitive_text)
    # Credentials replaced with [REDACTED:pattern_name]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------- Pattern registry ----------

_PATTERNS: list[tuple[str, re.Pattern[str]]] = []


def _register(name: str, pattern: str, flags: int = 0) -> None:
    _PATTERNS.append((name, re.compile(pattern, flags)))


# AWS
_register("aws_access_key", r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])")
_register(
    "aws_secret_key", r"(?<![A-Za-z0-9/+=])([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])"
)

# GitHub
_register("github_token", r"(ghp_[A-Za-z0-9]{36,})")
_register("github_oauth", r"(gho_[A-Za-z0-9]{36,})")
_register("github_app_token", r"(ghs_[A-Za-z0-9]{36,})")
_register("github_fine_grained", r"(github_pat_[A-Za-z0-9_]{22,})")

# Generic high-entropy secrets
_register(
    "generic_api_key",
    r"""(?i)(?:api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*[:=]\s*['"]?([A-Za-z0-9\-_.]{20,})['"]?""",
)

# Private keys
_register(
    "private_key", r"(-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----)", re.MULTILINE
)

# Connection strings
_register(
    "connection_string",
    r"(?i)((?:postgres|mysql|mongodb|redis)://[^\s'\"]+)",
)

# Bearer tokens in headers
_register("bearer_token", r"(?i)(?:bearer\s+)([A-Za-z0-9\-_.~+/]+=*)")


# ---------- Public API ----------


@dataclass
class RedactionResult:
    """Result of a redaction pass."""

    text: str
    redaction_count: int
    patterns_matched: list[str]


def scan(text: str) -> list[tuple[str, str]]:
    """Return a list of (pattern_name, matched_text) for all matches found."""
    hits: list[tuple[str, str]] = []
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            hits.append((name, match.group(1) if match.lastindex else match.group(0)))
    return hits


def redact(text: str) -> RedactionResult:
    """Replace all detected secrets with ``[REDACTED:pattern_name]`` placeholders."""
    result = text
    count = 0
    matched: list[str] = []

    for name, pattern in _PATTERNS:

        def _replacer(m: re.Match[str], _name: str = name) -> str:
            return f"[REDACTED:{_name}]"

        new_result, n = pattern.subn(_replacer, result)
        if n > 0:
            count += n
            matched.append(name)
            result = new_result

    return RedactionResult(text=result, redaction_count=count, patterns_matched=matched)
