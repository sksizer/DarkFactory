"""Unit tests for GitHub CLI subprocess primitives in _cli.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.utils._result import Ok
from darkfactory.utils.github._cli import gh_json, gh_run
from darkfactory.utils.github._types import GhErr


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(
    returncode: int = 1, stdout: str = "", stderr: str = "error"
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestGhRun:
    def test_ok_returns_ok_with_stdout(self) -> None:
        with patch(
            "darkfactory.utils.github._cli.subprocess.run",
            return_value=_ok(stdout="some output\n"),
        ):
            result = gh_run("pr", "list", cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value is None
        assert result.stdout == "some output\n"

    def test_nonzero_returns_gherr(self) -> None:
        with patch(
            "darkfactory.utils.github._cli.subprocess.run",
            return_value=_fail(returncode=1, stderr="not found"),
        ):
            result = gh_run("pr", "view", cwd=Path("/tmp"))
        assert isinstance(result, GhErr)
        assert result.returncode == 1
        assert result.stderr == "not found"
        assert result.cmd == ["gh", "pr", "view"]


class TestGhJson:
    def test_ok_returns_parsed_json(self) -> None:
        with patch(
            "darkfactory.utils.github._cli.subprocess.run",
            return_value=_ok(stdout='[{"state": "OPEN"}]'),
        ):
            result = gh_json("pr", "list", "--json", "state", cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value == [{"state": "OPEN"}]
        assert result.stdout == '[{"state": "OPEN"}]'

    def test_nonzero_returns_gherr(self) -> None:
        with patch(
            "darkfactory.utils.github._cli.subprocess.run",
            return_value=_fail(returncode=1, stderr="gh auth required"),
        ):
            result = gh_json("pr", "list", cwd=Path("/tmp"))
        assert isinstance(result, GhErr)
        assert result.returncode == 1
