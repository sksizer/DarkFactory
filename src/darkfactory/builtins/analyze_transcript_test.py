"""Unit tests for analyze_transcript builtin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from darkfactory.builtins.analyze_transcript import (
    analyze_transcript,
    append_summary,
    exceeds_threshold,
    find_transcript,
    invoke_llm,
    parse_transcript,
    run_detectors,
    write_analysis,
)
from darkfactory.builtins.analyze_transcript_detectors import Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> MagicMock:
    """Build a minimal ExecutionContext mock."""
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.cwd = tmp_path
    ctx.repo_root = tmp_path
    ctx.prd.id = "PRD-559"
    ctx.run_summary = None
    return ctx


def _write_transcript(tmp_path: Path, events: list[dict[str, Any]]) -> Path:
    """Write events as JSONL to the harness-transcripts location."""
    transcript_dir = tmp_path / ".harness-transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / "PRD-559.jsonl"
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    return path


_SAMPLE_WARNING_FINDING = Finding(
    category="tool_denied", severity="warning", message="Tool was blocked"
)
_SAMPLE_ERROR_FINDING = Finding(
    category="sentinel_failure", severity="error", message="Missing sentinel"
)
_SAMPLE_INFO_FINDING = Finding(
    category="large_thinking_burst", severity="info", message="Big thinking"
)

_DEFAULT_CONFIG = {
    "min_severity": "warning",
    "model_default": "haiku",
    "model_severe": "sonnet",
}


# ---------------------------------------------------------------------------
# Test: missing transcript — returns cleanly
# ---------------------------------------------------------------------------


def test_missing_transcript_returns_cleanly(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    # No transcript file created
    analyze_transcript(ctx)  # must not raise


def test_missing_transcript_no_subprocess(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    with patch("darkfactory.builtins.analyze_transcript.subprocess.run") as mock_run:
        analyze_transcript(ctx)
    mock_run.assert_not_called()


def test_missing_transcript_logs_info(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    with patch("darkfactory.builtins.analyze_transcript.logger") as mock_log:
        analyze_transcript(ctx)
    mock_log.info.assert_called()
    assert "skipping" in mock_log.info.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# Test: Stage 2 skipped when findings are below threshold (info only)
# ---------------------------------------------------------------------------


def test_stage2_skipped_for_info_only_findings(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    events = [
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "PRD_EXECUTE_OK"}]},
        }
    ]
    _write_transcript(tmp_path, events)

    with (
        patch(
            "darkfactory.builtins.analyze_transcript.run_detectors"
        ) as mock_detectors,
        patch("darkfactory.builtins.analyze_transcript.invoke_llm") as mock_llm,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_detectors.return_value = [_SAMPLE_INFO_FINDING]
        analyze_transcript(ctx)

    mock_llm.assert_not_called()


def test_stage2_skipped_appends_summary(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_transcript(tmp_path, [])

    with patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det:
        mock_det.return_value = [_SAMPLE_INFO_FINDING]
        analyze_transcript(ctx)

    # run_summary should be set
    assert ctx.run_summary is not None
    assert "Analysis" in ctx.run_summary


# ---------------------------------------------------------------------------
# Test: Stage 2 fires for warning-severity findings
# ---------------------------------------------------------------------------


def test_stage2_fires_for_warning_findings(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    _write_transcript(tmp_path, [])

    mock_proc = MagicMock()
    mock_proc.stdout = "## Summary\nAll good\n"

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run") as mock_run,
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        mock_run.return_value = mock_proc
        analyze_transcript(ctx)

    # subprocess.run called at least once (for claude)
    assert mock_run.call_count >= 1
    first_call_cmd = mock_run.call_args_list[0][0][0]
    assert "claude" in first_call_cmd


# ---------------------------------------------------------------------------
# Test: model selection is severity-tiered
# ---------------------------------------------------------------------------


def test_model_selection_warning_uses_model_default() -> None:
    findings = [_SAMPLE_WARNING_FINDING]
    config = _DEFAULT_CONFIG.copy()

    with patch("darkfactory.builtins.analyze_transcript.subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.stdout = "narrative"
        mock_run.return_value = mock_proc
        invoke_llm(findings, [], config)

    cmd = mock_run.call_args[0][0]
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "haiku"


def test_model_selection_error_uses_model_severe() -> None:
    findings = [_SAMPLE_ERROR_FINDING]
    config = _DEFAULT_CONFIG.copy()

    with patch("darkfactory.builtins.analyze_transcript.subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.stdout = "narrative"
        mock_run.return_value = mock_proc
        invoke_llm(findings, [], config)

    cmd = mock_run.call_args[0][0]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "sonnet"


# ---------------------------------------------------------------------------
# Test: dry-run mode
# ---------------------------------------------------------------------------


def test_dry_run_no_files_written(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run") as mock_run,
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        analyze_transcript(ctx)

    mock_run.assert_not_called()
    dest_dir = tmp_path / ".darkfactory" / "transcripts"
    assert not dest_dir.exists()


def test_dry_run_logs_intent(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.logger") as mock_log,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        analyze_transcript(ctx)

    info_calls = [str(c) for c in mock_log.info.call_args_list]
    assert any("dry" in c.lower() for c in info_calls)


# ---------------------------------------------------------------------------
# Test: LLM failure — logs warning, returns cleanly
# ---------------------------------------------------------------------------


def test_llm_failure_logs_warning_and_continues(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.invoke_llm") as mock_llm,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        mock_llm.side_effect = RuntimeError("LLM timeout")
        analyze_transcript(ctx)  # must not raise


def test_llm_failure_still_writes_analysis(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.invoke_llm") as mock_llm,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        mock_llm.side_effect = RuntimeError("LLM timeout")
        analyze_transcript(ctx)

    dest_dir = tmp_path / ".darkfactory" / "transcripts"
    files = list(dest_dir.glob("PRD-559-*.analysis.md"))
    assert len(files) == 1


# ---------------------------------------------------------------------------
# Test: ctx.run_summary augmented with analysis section
# ---------------------------------------------------------------------------


def test_run_summary_augmented_with_findings(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    ctx.run_summary = "## Existing summary\n- item"
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.invoke_llm") as mock_llm,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        mock_llm.return_value = "narrative text"
        analyze_transcript(ctx)

    assert ctx.run_summary is not None
    assert "Existing summary" in ctx.run_summary
    assert "Transcript Analysis" in ctx.run_summary


def test_run_summary_includes_analysis_file_path(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=False)
    _write_transcript(tmp_path, [])

    with (
        patch("darkfactory.builtins.analyze_transcript.run_detectors") as mock_det,
        patch("darkfactory.builtins.analyze_transcript.invoke_llm") as mock_llm,
        patch("darkfactory.builtins.analyze_transcript.subprocess.run"),
    ):
        mock_det.return_value = [_SAMPLE_WARNING_FINDING]
        mock_llm.return_value = "narrative"
        analyze_transcript(ctx)

    assert "analysis.md" in ctx.run_summary


# ---------------------------------------------------------------------------
# Test: AC-1 — builtin is registered and callable via BuiltIn("analyze_transcript")
# ---------------------------------------------------------------------------


def test_analyze_transcript_is_registered() -> None:
    from darkfactory.builtins._registry import BUILTINS
    import darkfactory.builtins.analyze_transcript  # noqa: F401  # trigger registration

    assert "analyze_transcript" in BUILTINS


# ---------------------------------------------------------------------------
# Test: helpers directly
# ---------------------------------------------------------------------------


def test_find_transcript_returns_none_when_missing(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert find_transcript(ctx) is None


def test_find_transcript_returns_path_when_present(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_transcript(tmp_path, [])
    result = find_transcript(ctx)
    assert result is not None
    assert result.exists()


def test_parse_transcript_parses_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    path.write_text('{"type": "assistant"}\n{"type": "user"}\n', encoding="utf-8")
    events = parse_transcript(path)
    assert len(events) == 2
    assert events[0]["type"] == "assistant"


def test_parse_transcript_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    path.write_text('{"type": "x"}\n\n{"type": "y"}\n', encoding="utf-8")
    events = parse_transcript(path)
    assert len(events) == 2


def test_run_detectors_isolates_crash() -> None:
    """A crashing detector should not prevent other detectors from running."""
    from darkfactory.builtins.analyze_transcript_detectors import DETECTORS

    def _crashing_detector(events: list[Any]) -> list[Any]:
        raise RuntimeError("boom")

    original = dict(DETECTORS)
    DETECTORS["_test_crash"] = _crashing_detector
    try:
        findings = run_detectors([])
    finally:
        DETECTORS.pop("_test_crash", None)
        # restore to original state
        for k in list(DETECTORS):
            if k not in original:
                DETECTORS.pop(k)

    # should not raise, findings from other detectors still collected
    assert isinstance(findings, list)


def test_exceeds_threshold_warning_with_warning_min() -> None:
    findings = [_SAMPLE_WARNING_FINDING]
    config = {
        "min_severity": "warning",
        "model_default": "haiku",
        "model_severe": "sonnet",
    }
    assert exceeds_threshold(findings, config) is True


def test_exceeds_threshold_info_below_warning_min() -> None:
    findings = [_SAMPLE_INFO_FINDING]
    config = {
        "min_severity": "warning",
        "model_default": "haiku",
        "model_severe": "sonnet",
    }
    assert exceeds_threshold(findings, config) is False


def test_exceeds_threshold_empty_findings() -> None:
    config = {
        "min_severity": "warning",
        "model_default": "haiku",
        "model_severe": "sonnet",
    }
    assert exceeds_threshold([], config) is False


def test_write_analysis_creates_file(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    findings = [_SAMPLE_WARNING_FINDING]
    path = write_analysis(ctx, findings, narrative="some narrative")
    assert path.exists()
    content = path.read_text()
    assert "Stage 1 Findings" in content
    assert "Stage 2 Narrative" in content
    assert "some narrative" in content


def test_write_analysis_no_narrative_skips_stage2_section(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    path = write_analysis(ctx, [], narrative=None)
    content = path.read_text()
    assert "Stage 2 Narrative" not in content


def test_append_summary_sets_run_summary(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    ctx.run_summary = None
    append_summary(ctx, [_SAMPLE_WARNING_FINDING], analysis_path=None)
    assert ctx.run_summary is not None
    assert "Transcript Analysis" in ctx.run_summary


def test_append_summary_appends_to_existing(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    ctx.run_summary = "existing content"
    append_summary(ctx, [], analysis_path=None)
    assert "existing content" in ctx.run_summary
    assert "Transcript Analysis" in ctx.run_summary
