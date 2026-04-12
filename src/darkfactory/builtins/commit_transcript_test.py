"""Unit tests for commit_transcript builtin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from darkfactory.builtins._test_helpers import make_builtin_ctx
from darkfactory.builtins.commit_transcript import commit_transcript


# ---------- no transcript file ----------


def test_no_transcript_skips_and_logs(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, prd_id="PRD-549.8")
    # No transcript file created — src will not exist
    commit_transcript(ctx)
    ctx.logger.info.assert_called()
    call_args = ctx.logger.info.call_args[0]
    assert "skipping" in call_args[0]


def test_no_transcript_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, prd_id="PRD-549.8")
    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        commit_transcript(ctx)
    mock_run.assert_not_called()


# ---------- dry-run path ----------


def test_dry_run_logs_intended_move(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True, prd_id="PRD-549.8")
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    commit_transcript(ctx)

    ctx.logger.info.assert_called()
    log_msg = ctx.logger.info.call_args[0][0]
    assert "[dry-run]" in log_msg


def test_dry_run_no_subprocess(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True, prd_id="PRD-549.8")
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    with patch("darkfactory.utils.git._run.subprocess.run") as mock_run:
        commit_transcript(ctx)
    mock_run.assert_not_called()


def test_dry_run_no_file_created(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=True, prd_id="PRD-549.8")
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    commit_transcript(ctx)

    dest_dir = tmp_path / ".darkfactory" / "transcripts"
    assert not dest_dir.exists()


# ---------- successful move and stage ----------


def test_successful_run_creates_dest_and_stages(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False, prd_id="PRD-549.8")
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    src = transcript_dir / "PRD-549.8.jsonl"
    src.write_text("transcript content")

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ) as mock_run:
        commit_transcript(ctx)

    # Destination directory should be created
    dest_dir = tmp_path / ".darkfactory" / "transcripts"
    assert dest_dir.exists()

    # A file matching the pattern should exist
    files = list(dest_dir.glob("PRD-549.8-*.jsonl"))
    assert len(files) == 1
    assert files[0].read_text() == "transcript content"

    # git add should be called
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "git"
    assert call_args[1] == "add"


def test_successful_run_logs_staged(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, dry_run=False, prd_id="PRD-549.8")
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("data")

    with patch(
        "darkfactory.utils.git._run.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], returncode=0, stdout="", stderr=""
        ),
    ):
        commit_transcript(ctx)

    ctx.logger.info.assert_called()
    log_msg = ctx.logger.info.call_args[0][0]
    assert "staged" in log_msg
