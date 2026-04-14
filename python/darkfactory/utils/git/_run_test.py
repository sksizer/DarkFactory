"""Unit tests for git subprocess primitives in _run.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.utils._result import Timeout
from darkfactory.utils.git._run import git_run
from darkfactory.utils.git._types import GitErr, Ok


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(
    returncode: int = 1, stdout: str = "", stderr: str = "error"
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestGitRun:
    def test_ok_returns_ok_with_stdout(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_ok(stdout="abc\n"),
        ):
            result = git_run("status", cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value is None
        assert result.stdout == "abc\n"

    def test_nonzero_returns_giterr_with_stdout_and_stderr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_fail(returncode=128, stdout="out", stderr="fatal: bad"),
        ):
            result = git_run("status", cwd=Path("/tmp"))
        assert isinstance(result, GitErr)
        assert result.returncode == 128
        assert result.stdout == "out"
        assert result.stderr == "fatal: bad"
        assert result.cmd == ["git", "status"]


class TestGitRunWithTimeout:
    def test_timeout_returns_timeout(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git", "ls-remote"], timeout=5),
        ):
            result = git_run("ls-remote", cwd=Path("/tmp"), timeout=5)
        assert isinstance(result, Timeout)
        assert result.cmd == ["git", "ls-remote"]
        assert result.timeout == 5

    def test_unexpected_exception_returns_giterr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            side_effect=OSError("no such file"),
        ):
            result = git_run("ls-remote", cwd=Path("/tmp"), timeout=10)
        assert isinstance(result, GitErr)
        assert result.returncode == -1
        assert "no such file" in result.stderr
        assert result.cmd == ["git", "ls-remote"]

    def test_ok_returns_ok(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_ok(stdout="ref\n"),
        ):
            result = git_run("ls-remote", cwd=Path("/tmp"), timeout=10)
        assert isinstance(result, Ok)
        assert result.value is None

    def test_nonzero_returns_giterr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_fail(returncode=2, stderr="not found"),
        ):
            result = git_run("ls-remote", cwd=Path("/tmp"), timeout=10)
        assert isinstance(result, GitErr)
        assert result.returncode == 2
