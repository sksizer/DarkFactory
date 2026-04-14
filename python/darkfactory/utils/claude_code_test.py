"""Tests for Claude Code subprocess helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from darkfactory.utils.claude_code import spawn_claude


def test_spawn_claude_passes_plain_argv_without_effort(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(argv: list[str], cwd: str, check: bool) -> object:
        captured.append(argv)

        class R:
            returncode = 0

        return R()

    with patch(
        "darkfactory.utils.claude_code._interactive.subprocess.run",
        side_effect=fake_run,
    ):
        exit_code = spawn_claude("hello", tmp_path)

    assert exit_code == 0
    assert captured == [["claude", "hello"]]


def test_spawn_claude_passes_effort_max_as_cli_flag(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(argv: list[str], cwd: str, check: bool) -> object:
        captured.append(argv)

        class R:
            returncode = 0

        return R()

    with patch(
        "darkfactory.utils.claude_code._interactive.subprocess.run",
        side_effect=fake_run,
    ):
        spawn_claude("hello", tmp_path, effort_level="max")

    assert captured == [["claude", "--effort", "max", "hello"]]


def test_spawn_claude_forwards_low_effort(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(argv: list[str], cwd: str, check: bool) -> object:
        captured.append(argv)

        class R:
            returncode = 0

        return R()

    with patch(
        "darkfactory.utils.claude_code._interactive.subprocess.run",
        side_effect=fake_run,
    ):
        spawn_claude("hello", tmp_path, effort_level="low")

    assert captured == [["claude", "--effort", "low", "hello"]]
