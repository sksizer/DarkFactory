"""Unit tests for commit_transcript builtin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.builtins.commit_transcript import commit_transcript


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    """Build a minimal ExecutionContext mock for commit_transcript tests."""
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.cwd = tmp_path
    ctx.repo_root = tmp_path
    ctx.prd.id = "PRD-549.8"
    return ctx


# ---------- no transcript file ----------


def test_no_transcript_skips_and_logs(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    # No transcript file created — src will not exist
    commit_transcript(ctx)
    ctx.jsonlger.info.assert_called()
    call_args = ctx.jsonlger.info.call_args[0]
    assert "skipping" in call_args[0]


def test_no_transcript_no_subprocess(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    with patch("darkfactory.builtins.commit_transcript.subprocess.run") as mock_run:
        commit_transcript(ctx)
    mock_run.assert_not_called()


# ---------- dry-run path ----------


def test_dry_run_logs_intended_move(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    commit_transcript(ctx)

    ctx.jsonlger.info.assert_called()
    log_msg = ctx.jsonlger.info.call_args[0][0]
    assert "[dry-run]" in log_msg


def test_dry_run_no_subprocess(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    with patch("darkfactory.builtins.commit_transcript.subprocess.run") as mock_run:
        commit_transcript(ctx)
    mock_run.assert_not_called()


def test_dry_run_no_file_created(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("transcript content")

    commit_transcript(ctx)

    dest_dir = tmp_path / ".darkfactory" / "transcripts"
    assert not dest_dir.exists()


# ---------- successful move and stage ----------


def test_successful_run_creates_dest_and_stages(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    src = transcript_dir / "PRD-549.8.jsonl"
    src.write_text("transcript content")

    with patch("darkfactory.builtins.commit_transcript.subprocess.run") as mock_run:
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
    ctx = _make_ctx(tmp_path, dry_run=False)
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "PRD-549.8.jsonl").write_text("data")

    with patch("darkfactory.builtins.commit_transcript.subprocess.run"):
        commit_transcript(ctx)

    ctx.jsonlger.info.assert_called()
    log_msg = ctx.jsonlger.info.call_args[0][0]
    assert "staged" in log_msg
