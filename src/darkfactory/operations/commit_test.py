"""Unit tests for commit builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.operations._test_helpers import make_builtin_ctx
from darkfactory.operations.commit import commit


# ---------- dry-run path ----------


def test_dry_run_logs_and_returns_without_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        commit(ctx, message="chore: test commit")
    mock_run.assert_not_called()
    ctx.logger.info.assert_called()


def test_dry_run_logs_formatted_message(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.format_string.side_effect = lambda s: s.replace("{prd_id}", "PRD-001")
    commit(ctx, message="chore(prd): {prd_id} start work")
    log_call = ctx.logger.info.call_args
    assert "PRD-001" in str(log_call)


# ---------- empty diff (no changes to commit) ----------


def test_empty_diff_skips_commit(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        if cmd[:3] == ["git", "diff", "--cached"]:
            result.returncode = 0  # nothing staged
        else:
            result.returncode = 0
        return result

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        commit(ctx, message="chore: test")

    ctx.logger.info.assert_called_with("commit skipped: no changes to commit")


def test_empty_diff_does_not_call_git_commit(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        return result

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        commit(ctx, message="chore: test")

    assert not any("commit" in c and "-m" in c for c in calls)


# ---------- successful commit ----------


def test_successful_commit_calls_git_add_then_commit(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        calls.append(list(cmd))
        result = MagicMock()
        # diff --cached --quiet returns 1 when there ARE staged changes
        result.returncode = 1 if cmd[:3] == ["git", "diff", "--cached"] else 0
        return result

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        commit(ctx, message="chore: my commit")

    assert calls[0] == ["git", "add", "-A"]
    assert calls[2] == ["git", "commit", "-m", "chore: my commit"]


def test_successful_commit_uses_formatted_message(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.format_string.side_effect = lambda s: s.replace("{prd_id}", "PRD-042")
    committed_messages: list[str] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 1 if cmd[:3] == ["git", "diff", "--cached"] else 0
        if "commit" in cmd and "-m" in cmd:
            idx = cmd.index("-m")
            committed_messages.append(cmd[idx + 1])
        return result

    with patch("darkfactory.utils.git._run.subprocess.run", side_effect=fake_run):
        commit(ctx, message="chore(prd): {prd_id} start work")

    assert committed_messages == ["chore(prd): PRD-042 start work"]


# ---------- forbidden attribution ----------


def test_forbidden_attribution_raises_before_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path)
    ctx.format_string.side_effect = lambda s: s

    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        with pytest.raises(RuntimeError, match="forbidden attribution"):
            commit(
                ctx,
                message="chore: fix Co-Authored-By: Claude Code <noreply@anthropic.com>",
            )

    mock_run.assert_not_called()


def test_forbidden_attribution_raises_in_dry_run(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True)
    ctx.format_string.side_effect = lambda s: s

    with pytest.raises(RuntimeError, match="forbidden attribution"):
        commit(
            ctx,
            message="chore: fix Co-Authored-By: Claude Code <noreply@anthropic.com>",
        )
