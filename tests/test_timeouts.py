"""Unit tests for darkfactory.timeouts.resolve_timeout."""

from __future__ import annotations

from typing import Any

import pytest

from darkfactory.timeouts import (
    DEFAULT_EFFORT_TIMEOUTS,
    resolve_timeout,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default(effort: str, capability: str = "simple") -> tuple[int, str]:
    """Shorthand: call resolve_timeout with no overrides."""
    return resolve_timeout(
        effort=effort,
        capability=capability,
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )


# ---------------------------------------------------------------------------
# AC-1: Built-in effort tiers (no multiplier effect at 1.0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "effort, expected_seconds",
    [
        ("xs", 300),
        ("s", 600),
        ("m", 1200),
        ("l", 2400),
        ("xl", 4500),
    ],
)
def test_default_effort_tiers(effort: str, expected_seconds: int) -> None:
    seconds, source = _default(effort)
    assert seconds == expected_seconds
    assert source == "default"


# ---------------------------------------------------------------------------
# AC-2: Capability multipliers applied on top of effort base
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability, multiplier",
    [
        ("trivial", 1.0),
        ("simple", 1.0),
        ("moderate", 1.25),
        ("complex", 1.5),
    ],
)
def test_capability_multipliers(capability: str, multiplier: float) -> None:
    base = DEFAULT_EFFORT_TIMEOUTS["m"]  # 1200 s
    expected = int(base * multiplier)
    seconds, source = resolve_timeout(
        effort="m",
        capability=capability,
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == expected
    assert source == "default"


def test_unknown_capability_uses_multiplier_one() -> None:
    base = DEFAULT_EFFORT_TIMEOUTS["s"]
    seconds, source = resolve_timeout(
        effort="s",
        capability="unknown-tier",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == base
    assert source == "default"


def test_none_capability_uses_multiplier_one() -> None:
    base = DEFAULT_EFFORT_TIMEOUTS["s"]
    seconds, source = resolve_timeout(
        effort="s",
        capability=None,
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == base
    assert source == "default"


# ---------------------------------------------------------------------------
# AC-3: PRD frontmatter overrides computed value
# ---------------------------------------------------------------------------


def test_prd_frontmatter_overrides_default() -> None:
    seconds, source = resolve_timeout(
        effort="xl",
        capability="complex",
        timeout_minutes_frontmatter=7,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == 7 * 60
    assert source == "prd_frontmatter"


def test_prd_frontmatter_overrides_config() -> None:
    config = {"s": 99}
    seconds, source = resolve_timeout(
        effort="s",
        capability="simple",
        timeout_minutes_frontmatter=3,
        config_timeouts=config,
        cli_override=None,
    )
    assert seconds == 3 * 60
    assert source == "prd_frontmatter"


# ---------------------------------------------------------------------------
# AC-4: CLI override takes precedence over everything
# ---------------------------------------------------------------------------


def test_cli_overrides_frontmatter_and_config() -> None:
    config = {"s": 99}
    seconds, source = resolve_timeout(
        effort="s",
        capability="complex",
        timeout_minutes_frontmatter=30,
        config_timeouts=config,
        cli_override=5,
    )
    assert seconds == 5 * 60
    assert source == "cli"


def test_cli_overrides_default() -> None:
    seconds, source = resolve_timeout(
        effort="xl",
        capability="complex",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=2,
    )
    assert seconds == 2 * 60
    assert source == "cli"


# ---------------------------------------------------------------------------
# AC-5: Config table overrides built-in defaults
# ---------------------------------------------------------------------------


def test_config_overrides_builtin_default() -> None:
    config = {"s": 30}  # 30 minutes instead of 10
    seconds, source = resolve_timeout(
        effort="s",
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=config,
        cli_override=None,
    )
    assert seconds == 30 * 60
    assert source == "config"


def test_config_applies_capability_multiplier() -> None:
    config = {"m": 20}  # 20 minutes base
    seconds, source = resolve_timeout(
        effort="m",
        capability="complex",
        timeout_minutes_frontmatter=None,
        config_timeouts=config,
        cli_override=None,
    )
    # 20 min × 1.5 × 60 s/min = 1800 s
    assert seconds == int(20 * 60 * 1.5)
    assert source == "config"


def test_config_missing_effort_falls_back_to_default() -> None:
    # Config has entries for other tiers but not "l".
    config = {"s": 15, "m": 25}
    seconds, source = resolve_timeout(
        effort="l",
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=config,
        cli_override=None,
    )
    assert seconds == DEFAULT_EFFORT_TIMEOUTS["l"]
    assert source == "default"


# ---------------------------------------------------------------------------
# AC-6: Function returns both timeout value and source string
# ---------------------------------------------------------------------------


def test_return_type_is_tuple_int_str() -> None:
    result = resolve_timeout(
        effort="s",
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    seconds, source = result
    assert isinstance(seconds, int)
    assert isinstance(source, str)


@pytest.mark.parametrize(
    "kwargs, expected_source",
    [
        ({"cli_override": 5}, "cli"),
        ({"timeout_minutes_frontmatter": 10}, "prd_frontmatter"),
        ({"config_timeouts": {"s": 15}}, "config"),
        ({}, "default"),
    ],
)
def test_source_strings(kwargs: dict[str, Any], expected_source: str) -> None:
    base: dict[str, Any] = dict(
        effort="s",
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    base.update(kwargs)
    _, source = resolve_timeout(**base)
    assert source == expected_source


# ---------------------------------------------------------------------------
# Missing effort fallback (req 7)
# ---------------------------------------------------------------------------


def test_missing_effort_falls_back_to_s() -> None:
    seconds, source = resolve_timeout(
        effort=None,
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == DEFAULT_EFFORT_TIMEOUTS["s"]
    assert source == "default"


def test_unknown_effort_falls_back_to_s() -> None:
    seconds, source = resolve_timeout(
        effort="xxl",
        capability="simple",
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    assert seconds == DEFAULT_EFFORT_TIMEOUTS["s"]
    assert source == "default"
