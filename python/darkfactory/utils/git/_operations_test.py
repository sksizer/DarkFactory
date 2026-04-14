"""Unit tests for git operation helpers in _operations.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.utils.git._operations import (
    diff_quiet,
    run_add,
    run_commit,
    status_other_dirty,
)
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


class TestDiffQuiet:
    def test_clean_returns_ok(self) -> None:
        with patch("darkfactory.utils.git._run.subprocess.run", return_value=_ok()):
            result = diff_quiet(["file.py"], cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value is None

    def test_dirty_returns_giterr(self) -> None:
        with patch("darkfactory.utils.git._run.subprocess.run", return_value=_fail()):
            result = diff_quiet(["file.py"], cwd=Path("/tmp"))
        assert isinstance(result, GitErr)
        assert result.returncode == 1


class TestRunAdd:
    def test_failure_returns_giterr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_fail(returncode=128, stderr="fatal: pathspec"),
        ):
            result = run_add(["nonexistent.py"], cwd=Path("/tmp"))
        assert isinstance(result, GitErr)
        assert result.returncode == 128


class TestRunCommit:
    def test_failure_returns_giterr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_fail(returncode=1, stderr="nothing to commit"),
        ):
            result = run_commit("test message", cwd=Path("/tmp"))
        assert isinstance(result, GitErr)
        assert result.returncode == 1


class TestStatusOtherDirty:
    def test_returns_ok_with_filtered_files(self) -> None:
        porcelain = " M file.py\n M other.py\n?? new.txt\n"
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_ok(stdout=porcelain),
        ):
            result = status_other_dirty(["file.py"], cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value == ["other.py", "new.txt"]
        assert result.stdout == porcelain

    def test_returns_empty_when_all_in_paths(self) -> None:
        porcelain = " M file.py\n"
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_ok(stdout=porcelain),
        ):
            result = status_other_dirty(["file.py"], cwd=Path("/tmp"))
        assert isinstance(result, Ok)
        assert result.value == []

    def test_git_failure_returns_giterr(self) -> None:
        with patch(
            "darkfactory.utils.git._run.subprocess.run",
            return_value=_fail(returncode=128, stderr="fatal"),
        ):
            result = status_other_dirty(["file.py"], cwd=Path("/tmp"))
        assert isinstance(result, GitErr)
