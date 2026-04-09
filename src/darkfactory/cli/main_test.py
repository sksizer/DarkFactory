"""Smoke tests for the CLI entry point."""

from __future__ import annotations

import pytest

from darkfactory.cli.main import main


def test_main_no_args_exits_nonzero() -> None:
    """main() with no arguments should exit non-zero (missing subcommand)."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_main_help_exits_zero() -> None:
    """main(['--help']) should exit with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_main_is_callable() -> None:
    """main is importable and callable."""
    assert callable(main)
