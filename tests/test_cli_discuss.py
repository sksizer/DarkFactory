"""Integration tests for ``prd discuss`` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import write_prd
from darkfactory.cli._parser import build_parser


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with a PRD and return prd_dir."""
    (tmp_path / ".git").mkdir()
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "test-prd", title="Test PRD")
    return prd_dir


def test_discuss_registered_in_parser() -> None:
    """AC-1: ``prd discuss`` is a registered subcommand."""
    parser = build_parser()
    args = parser.parse_args(["discuss", "PRD-070"])
    assert args.prd_id == "PRD-070"
    assert hasattr(args, "func")


def test_discuss_unknown_prd_exits(tmp_path: Path) -> None:
    """AC-1: Running on an unknown PRD exits cleanly."""
    prd_dir = _setup_project(tmp_path)

    parser = build_parser()
    args = parser.parse_args(["discuss", "PRD-999"])
    args.prd_dir = prd_dir
    args.operations_dir = tmp_path / "operations"

    with patch("darkfactory.cli.discuss.shutil") as mock_shutil:
        mock_shutil.which.return_value = "/usr/bin/claude"
        with pytest.raises(SystemExit, match="unknown PRD id"):
            args.func(args)


def test_discuss_missing_claude_exits(tmp_path: Path) -> None:
    """AC-7: Missing ``claude`` binary exits before the chain runs."""
    prd_dir = _setup_project(tmp_path)

    parser = build_parser()
    args = parser.parse_args(["discuss", "PRD-070"])
    args.prd_dir = prd_dir
    args.operations_dir = tmp_path / "operations"

    with patch("darkfactory.cli.discuss.shutil") as mock_shutil:
        mock_shutil.which.side_effect = lambda name: (
            None if name == "claude" else "/usr/bin/git"
        )
        with pytest.raises(SystemExit, match="claude.*not on PATH"):
            args.func(args)


def test_discuss_launches_chain(tmp_path: Path) -> None:
    """AC-6: The discuss chain dispatches through the system runner."""
    prd_dir = _setup_project(tmp_path)

    parser = build_parser()
    args = parser.parse_args(["discuss", "PRD-070"])
    args.prd_dir = prd_dir
    args.operations_dir = tmp_path / "operations"

    with patch("darkfactory.cli.discuss.shutil") as mock_shutil:
        mock_shutil.which.return_value = "/usr/bin/claude"
        with patch("darkfactory.cli.discuss.run_system_operation") as mock_run:
            from darkfactory.system_runner import RunResult

            mock_run.return_value = RunResult(success=True)
            result = args.func(args)

    assert result == 0
    mock_run.assert_called_once()
    ctx = mock_run.call_args[0][1]
    assert ctx.target_prd == "PRD-070"


def test_new_discuss_flag_registered() -> None:
    """AC-2: ``--discuss`` flag exists on ``prd new``."""
    parser = build_parser()
    args = parser.parse_args(["new", "--discuss", "Some Title"])
    assert args.discuss is True


def test_new_discuss_composes_with_open() -> None:
    """AC-2: ``--discuss`` and ``--open`` can be used together."""
    parser = build_parser()
    args = parser.parse_args(["new", "--discuss", "--open", "Some Title"])
    assert args.discuss is True
    assert args.open is True


def test_discuss_help_describes_chain() -> None:
    """AC-11: ``prd discuss --help`` and ``prd new --help`` describe the commands."""
    parser = build_parser()
    sub_actions = [
        a for a in parser._subparsers._actions if hasattr(a, "_parser_class")
    ]
    found = False
    for action in sub_actions:
        if hasattr(action, "choices") and "discuss" in action.choices:
            discuss_parser = action.choices["discuss"]
            discuss_help = discuss_parser.format_help().lower()
            assert "discussion" in discuss_help
            assert "phase" in discuss_help

            new_parser = action.choices["new"]
            new_help = new_parser.format_help().lower()
            assert "--discuss" in new_help
            found = True
            break
    assert found, "discuss subcommand not found in parser"
