"""TUI display helpers."""

from __future__ import annotations

import sys


def print_phase_banner(phase: str) -> None:
    """Print a phase banner to stderr."""
    bar = "\u2500" * 37
    print(bar, file=sys.stderr)
    print(f" Phase: {phase}", file=sys.stderr)
    print(" Press Ctrl-C now to abort the chain.", file=sys.stderr)
    print(bar, file=sys.stderr)
