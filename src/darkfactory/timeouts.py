"""Timeout resolution for agent tasks.

Computes a task timeout in seconds using a priority-ordered resolution chain:

1. CLI override (minutes) — highest priority
2. PRD frontmatter ``timeout_minutes`` field
3. Config table lookup (``[timeouts]`` in ``.darkfactory/config.toml``) × capability multiplier
4. Built-in effort → second defaults × capability multiplier
"""

from __future__ import annotations

from typing import Any

DEFAULT_EFFORT_TIMEOUTS: dict[str, int] = {
    "xs": 300,
    "s": 600,
    "m": 1200,
    "l": 2400,
    "xl": 4500,
}

CAPABILITY_MULTIPLIERS: dict[str, float] = {
    "trivial": 1.0,
    "simple": 1.0,
    "moderate": 1.25,
    "complex": 1.5,
}

_DEFAULT_EFFORT = "s"


def resolve_timeout(
    effort: str | None,
    capability: str | None,
    timeout_minutes_frontmatter: int | None,
    config_timeouts: dict[str, Any] | None,
    cli_override: int | None,
) -> tuple[int, str]:
    """Return ``(timeout_seconds, source_description)``.

    Parameters
    ----------
    effort:
        PRD effort tier (``xs``, ``s``, ``m``, ``l``, ``xl``).  ``None`` or
        unrecognised values fall back to ``"s"``.
    capability:
        PRD capability tier (``trivial``, ``simple``, ``moderate``,
        ``complex``).  ``None`` or unrecognised values use a multiplier of 1.0.
    timeout_minutes_frontmatter:
        Value of the PRD's ``timeout_minutes`` frontmatter field, if set.
    config_timeouts:
        The ``[timeouts]`` section from ``.darkfactory/config.toml`` as a dict,
        or ``None`` if the section is absent.  Effort keys map to *minutes*;
        a nested ``capability_multipliers`` key (if present) is ignored here
        because the caller already resolved the section.
    cli_override:
        Integer minutes passed via a CLI flag.  Takes precedence over everything.

    Returns
    -------
    tuple[int, str]
        ``(seconds, source)`` where *source* is one of ``"cli"``,
        ``"prd_frontmatter"``, ``"config"``, or ``"default"``.
    """
    # 1. CLI override.
    if cli_override is not None:
        return cli_override * 60, "cli"

    # 2. PRD frontmatter.
    if timeout_minutes_frontmatter is not None:
        return timeout_minutes_frontmatter * 60, "prd_frontmatter"

    # Resolve multiplier (falls back to 1.0 for unknown / missing capability).
    multiplier = CAPABILITY_MULTIPLIERS.get(capability or "", 1.0)

    # Normalise effort — fall back to default for unknown / missing values.
    normalised_effort = effort if effort in DEFAULT_EFFORT_TIMEOUTS else _DEFAULT_EFFORT

    # 3. Config table.
    if config_timeouts is not None:
        # Config stores minutes; capability_multipliers sub-key is a nested dict.
        config_minutes = config_timeouts.get(normalised_effort)
        if config_minutes is not None:
            return int(config_minutes * 60 * multiplier), "config"

    # 4. Built-in defaults.
    base_seconds = DEFAULT_EFFORT_TIMEOUTS[normalised_effort]
    return int(base_seconds * multiplier), "default"
