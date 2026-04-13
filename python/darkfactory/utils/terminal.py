"""Terminal input helpers."""

from __future__ import annotations


def prompt_user(prompt: str) -> str:
    """Read user input. Extracted for testability."""
    return input(prompt)
