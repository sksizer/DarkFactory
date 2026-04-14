"""Unit tests for analyze_transcript builtin."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.engine import CodeEnv, PrdWorkflowRun, WorktreeState
from darkfactory.operations._test_helpers import _make_test_prd
from darkfactory.operations.analyze_transcript import (
    _find_transcript,
    _load_analysis_config,
    _parse_transcript,
    analyze_transcript,
)
from darkfactory.workflow import RunContext, Workflow


# ---------- Context factory ----------


def _make_ctx(tmp_path: Path, *, dry_run: bool = False) -> RunContext:
    prd = _make_test_prd(prd_id="PRD-559", repo_root=tmp_path)
    ctx = RunContext(dry_run=dry_run)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=Workflow(name="test", tasks=[])))
    ctx.state.put(WorktreeState(branch="prd/PRD-559-test", base_ref="main"))
    return ctx


# ---------- _find_transcript ----------


def test_find_transcript_in_worktree(tmp_path: Path) -> None:
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    f = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    f.write_text("{}")
    ctx = _make_ctx(tmp_path)
    result = _find_transcript(ctx)
    assert result == f


def test_find_transcript_fallback_to_harness(tmp_path: Path) -> None:
    src = tmp_path / ".harness-transcripts"
    src.mkdir()
    f = src / "PRD-559.jsonl"
    f.write_text("{}")
    ctx = _make_ctx(tmp_path)
    result = _find_transcript(ctx)
    assert result == f


def test_find_transcript_none_when_missing(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    assert _find_transcript(ctx) is None


def test_find_transcript_returns_latest(tmp_path: Path) -> None:
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    older = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    newer = td / "PRD-559-2026-01-02T00-00-00.jsonl"
    older.write_text("{}")
    newer.write_text("{}")
    ctx = _make_ctx(tmp_path)
    result = _find_transcript(ctx)
    assert result == newer


# ---------- _parse_transcript ----------


def _make_transcript(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.jsonl"
    p.write_text(content)
    return p


def test_parse_jsonl_events(tmp_path: Path) -> None:
    ev1 = {"type": "system", "subtype": "init"}
    ev2 = {"type": "assistant", "message": {"content": []}}
    content = json.dumps(ev1) + "\n" + json.dumps(ev2) + "\n"
    path = _make_transcript(tmp_path, content)
    events = _parse_transcript(path)
    assert len(events) == 2
    assert events[0]["type"] == "system"


def test_parse_invalid_json_skipped(tmp_path: Path) -> None:
    content = "not-json\n"
    path = _make_transcript(tmp_path, content)
    events = _parse_transcript(path)
    assert events == []


def test_parse_blank_lines_skipped(tmp_path: Path) -> None:
    ev1 = {"type": "system"}
    content = "\n" + json.dumps(ev1) + "\n\n"
    path = _make_transcript(tmp_path, content)
    events = _parse_transcript(path)
    assert len(events) == 1


def test_parse_comment_lines_skipped(tmp_path: Path) -> None:
    ev1 = {"type": "system"}
    content = "# this is a comment\n" + json.dumps(ev1) + "\n"
    path = _make_transcript(tmp_path, content)
    events = _parse_transcript(path)
    assert len(events) == 1


# ---------- _load_analysis_config ----------


def test_load_config_missing_file(tmp_path: Path) -> None:
    cfg = _load_analysis_config(tmp_path)
    assert cfg == {}


def test_load_config_reads_analysis_section(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".darkfactory"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[analysis]\nmin_severity = "error"\nmodel_default = "haiku"\n'
    )
    cfg = _load_analysis_config(tmp_path)
    assert cfg["min_severity"] == "error"
    assert cfg["model_default"] == "haiku"


def test_load_config_no_analysis_section(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".darkfactory"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("[timeouts]\nxs = 5\n")
    cfg = _load_analysis_config(tmp_path)
    assert cfg == {}


# ---------- analyze_transcript builtin ----------


def _make_transcript_file(tmp_path: Path) -> Path:
    """Create a minimal committed transcript in the worktree."""
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    ok_event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "PRD_EXECUTE_OK: PRD-559"}]},
    }
    content = json.dumps(ok_event) + "\n"
    path.write_text(content)
    return path


def test_dry_run_logs_and_returns(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, dry_run=True)
    _make_transcript_file(tmp_path)
    with patch("darkfactory.operations.analyze_transcript.claude_print") as mock_cp:
        analyze_transcript(ctx)
    mock_cp.assert_not_called()
    # dry-run path returns without error — that's the contract


def test_no_transcript_logs_warning_and_returns(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    analyze_transcript(ctx)
    # No transcript -> run_summary should not be set
    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.run_summary is None


def test_info_only_findings_skip_stage2(tmp_path: Path) -> None:
    """AC-4: Stage 2 skipped when max severity < min_severity (default: warning)."""
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    # Large thinking block produces info-level finding; sentinel OK present
    big_thought = "x" * 8001  # 8001 chars / 4 = 2000 tokens, triggers threshold
    thinking_event = {
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": big_thought}]},
    }
    ok_event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "PRD_EXECUTE_OK: PRD-559"}]},
    }
    content = json.dumps(thinking_event) + "\n" + json.dumps(ok_event) + "\n"
    path.write_text(content)
    ctx = _make_ctx(tmp_path)

    with patch("darkfactory.operations.analyze_transcript.claude_print") as mock_cp:
        analyze_transcript(ctx)

    # Stage 2 LLM should not fire for info-only findings
    mock_cp.assert_not_called()


def test_warning_findings_use_model_default(tmp_path: Path) -> None:
    """AC-4b: warning-severity findings use model_default (haiku by default)."""
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    # tool_denied produces warning; add sentinel OK to avoid error-level sentinel_failure
    denied_event = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "is_error": True,
                    "content": "This operation requires approval",
                }
            ]
        },
    }
    ok_event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "PRD_EXECUTE_OK: PRD-559"}]},
    }
    content = json.dumps(denied_event) + "\n" + json.dumps(ok_event) + "\n"
    path.write_text(content)
    ctx = _make_ctx(tmp_path)

    llm_calls: list[list[str]] = []

    def _fake_claude_print(
        prompt: str,
        *,
        model: str,
        cwd: object,
        allowed_tools: object = None,
        timeout: int = 120,
    ) -> MagicMock:
        llm_calls.append(["--model", model])
        r = MagicMock()
        r.returncode = 0
        r.stdout = "## Summary\n\nOK\n\n### Findings\n\nNone\n\n### Recommendations\n\nNone\n\n### Suggested PRD\n\n(none)\n"
        return r

    with patch(
        "darkfactory.operations.analyze_transcript.claude_print",
        side_effect=_fake_claude_print,
    ):
        analyze_transcript(ctx)

    assert len(llm_calls) == 1
    assert "--model" in llm_calls[0]
    model_idx = llm_calls[0].index("--model")
    assert llm_calls[0][model_idx + 1] == "haiku"


def test_error_findings_use_model_severe(tmp_path: Path) -> None:
    """AC-4b: error-severity findings use model_severe (sonnet by default)."""
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    # No PRD_EXECUTE_OK -> sentinel_failure gives error
    content = '{"type":"assistant","message":{"content":[{"type":"text","text":"I am done"}]}}\n'
    path.write_text(content)
    ctx = _make_ctx(tmp_path)

    llm_calls: list[list[str]] = []

    def _fake_claude_print(
        prompt: str,
        *,
        model: str,
        cwd: object,
        allowed_tools: object = None,
        timeout: int = 120,
    ) -> MagicMock:
        llm_calls.append(["--model", model])
        r = MagicMock()
        r.returncode = 0
        r.stdout = "narrative text"
        return r

    with patch(
        "darkfactory.operations.analyze_transcript.claude_print",
        side_effect=_fake_claude_print,
    ):
        analyze_transcript(ctx)

    assert len(llm_calls) == 1
    model_idx = llm_calls[0].index("--model")
    assert llm_calls[0][model_idx + 1] == "sonnet"


def test_analysis_file_written_not_staged_by_default(tmp_path: Path) -> None:
    """AC-5: analysis.md is written but NOT staged by default (security)."""
    _make_transcript_file(tmp_path)
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.operations.analyze_transcript.git_run",
    ) as mock_git:
        analyze_transcript(ctx)

    # An analysis file should exist
    td = tmp_path / ".darkfactory" / "transcripts"
    analysis_files = list(td.glob("*.analysis.md"))
    assert len(analysis_files) == 1

    # git_run should NOT have been called (default: no commit)
    mock_git.assert_not_called()


def test_analysis_file_staged_when_config_commit_true(tmp_path: Path) -> None:
    """AC-5: analysis.md is staged when [analysis] commit = true."""
    _make_transcript_file(tmp_path)
    ctx = _make_ctx(tmp_path)

    # Write config enabling commit
    config_dir = tmp_path / ".darkfactory"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text('[analysis]\ncommit = "true"\n')

    from darkfactory.utils import Ok as _Ok

    with patch(
        "darkfactory.operations.analyze_transcript.git_run",
        return_value=_Ok(None),
    ) as mock_git:
        analyze_transcript(ctx)

    # git_run should have been called for staging
    mock_git.assert_called_once()
    call_args = mock_git.call_args
    assert call_args[0][0] == "add"


def test_run_summary_augmented(tmp_path: Path) -> None:
    """AC-6: ctx.run_summary is augmented with analysis section."""
    _make_transcript_file(tmp_path)
    ctx = _make_ctx(tmp_path)
    # Seed an existing run_summary via PrdWorkflowRun
    prd_run = ctx.state.get(PrdWorkflowRun)
    ctx.state.put(
        PrdWorkflowRun(
            prd=prd_run.prd,
            workflow=prd_run.workflow,
            run_summary="## Harness execution summary\n\n- **Workflow:** default\n",
        )
    )

    analyze_transcript(ctx)

    updated_run = ctx.state.get(PrdWorkflowRun)
    assert updated_run.run_summary is not None
    assert "## Transcript analysis" in updated_run.run_summary
    # Original content preserved
    assert "Harness execution summary" in updated_run.run_summary


def test_run_summary_set_when_none(tmp_path: Path) -> None:
    """ctx.run_summary starts None -- analyze_transcript sets it."""
    _make_transcript_file(tmp_path)
    ctx = _make_ctx(tmp_path)
    prd_run = ctx.state.get(PrdWorkflowRun)
    assert prd_run.run_summary is None

    analyze_transcript(ctx)

    updated_run = ctx.state.get(PrdWorkflowRun)
    assert updated_run.run_summary is not None
    assert "Transcript analysis" in updated_run.run_summary


def test_scanner_exception_does_not_fail_workflow(tmp_path: Path) -> None:
    """AC-7: scanner failure is advisory -- builtin returns cleanly."""
    _make_transcript_file(tmp_path)
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.operations.analyze_transcript._parse_transcript",
        side_effect=RuntimeError("boom"),
    ):
        # Should not raise
        analyze_transcript(ctx)


def test_llm_failure_does_not_fail_workflow(tmp_path: Path) -> None:
    """AC-7: LLM call failure is advisory -- builtin returns cleanly."""
    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(parents=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    # No sentinel OK -> sentinel_failure = error -> LLM fires
    content = (
        '{"type":"assistant","message":{"content":[{"type":"text","text":"done"}]}}\n'
    )
    path.write_text(content)
    ctx = _make_ctx(tmp_path)

    with patch(
        "darkfactory.operations.analyze_transcript.claude_print",
        side_effect=RuntimeError("LLM subprocess failed"),
    ):
        # Should not raise
        analyze_transcript(ctx)


def test_config_min_severity_respected(tmp_path: Path) -> None:
    """AC-4: min_severity=error means warning findings skip Stage 2."""
    cfg_dir = tmp_path / ".darkfactory"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('[analysis]\nmin_severity = "error"\n')

    td = tmp_path / ".darkfactory" / "transcripts"
    td.mkdir(exist_ok=True)
    path = td / "PRD-559-2026-01-01T00-00-00.jsonl"
    # tool_denied = warning; sentinel OK present
    denied = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "is_error": True,
                    "content": "requires approval",
                }
            ]
        },
    }
    ok = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "PRD_EXECUTE_OK: PRD-559"}]},
    }
    content = json.dumps(denied) + "\n" + json.dumps(ok) + "\n"
    path.write_text(content)
    ctx = _make_ctx(tmp_path)

    with patch("darkfactory.operations.analyze_transcript.claude_print") as mock_cp:
        analyze_transcript(ctx)

    # min_severity=error, max severity was warning -> Stage 2 should not fire
    mock_cp.assert_not_called()
