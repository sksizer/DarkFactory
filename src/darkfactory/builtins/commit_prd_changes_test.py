"""Tests for commit_prd_changes system builtin."""

from __future__ import annotations

import subprocess as sp
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import init_git_repo, make_system_ctx, setup_repo_with_prd, write_prd
from darkfactory.builtins.commit_prd_changes import commit_prd_changes
from darkfactory.prd import load_all


def test_no_changes_returns_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "test-prd")
    prds = load_all(prd_dir)

    sp.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    sp.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")
    commit_prd_changes(ctx)

    captured = capsys.readouterr()
    assert "No PRD changes to commit" in captured.err


def test_user_accepts_commit(tmp_path: Path) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    with patch("darkfactory.builtins.commit_prd_changes.prompt_user", return_value="y"):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    result = sp.run(
        ["git", "log", "--oneline", "-1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "discuss session refinements" in result.stdout


def test_user_skips_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    with patch("darkfactory.builtins.commit_prd_changes.prompt_user", return_value="n"):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    captured = capsys.readouterr()
    assert "Skipped commit" in captured.err


def test_user_default_skips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    with patch("darkfactory.builtins.commit_prd_changes.prompt_user", return_value=""):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    captured = capsys.readouterr()
    assert "Skipped commit" in captured.err


def test_user_edits_message(tmp_path: Path) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    responses = iter(["e", "custom commit message"])
    with patch(
        "darkfactory.builtins.commit_prd_changes.prompt_user", side_effect=responses
    ):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    result = sp.run(
        ["git", "log", "--oneline", "-1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "custom commit message" in result.stdout


def test_other_dirty_files_noted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    (tmp_path / "other.txt").write_text("unrelated change\n", encoding="utf-8")

    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    with patch("darkfactory.builtins.commit_prd_changes.prompt_user", return_value="y"):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    captured = capsys.readouterr()
    assert "other file(s)" in captured.err

    result = sp.run(
        ["git", "status", "--porcelain"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "other.txt" in result.stdout


def test_commit_only_target_prd_file(tmp_path: Path) -> None:
    _, prds = setup_repo_with_prd(tmp_path)
    (tmp_path / "other.txt").write_text("unrelated\n", encoding="utf-8")

    ctx = make_system_ctx(tmp_path, prds=prds, target_prd="PRD-070")

    with patch("darkfactory.builtins.commit_prd_changes.prompt_user", return_value="y"):
        with patch("darkfactory.builtins.commit_prd_changes.diff_show"):
            commit_prd_changes(ctx)

    result = sp.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    committed_files = result.stdout.strip().splitlines()
    assert len(committed_files) == 1
    assert "PRD-070" in committed_files[0]


def test_no_push_no_pr(tmp_path: Path) -> None:
    import inspect

    from darkfactory.builtins import commit_prd_changes as module

    source = inspect.getsource(module)
    assert "git push" not in source.lower()
    assert "create_pr" not in source.lower()
    assert "gh pr" not in source.lower()
