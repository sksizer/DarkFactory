"""Built-in: analyze_transcript -- scan agent run transcripts for problem signals.

Two-stage pipeline:

1. **Stage 1** -- deterministic Python scan via registered detectors.
   Returns a list of :class:`~analyze_transcript_detectors.Finding` records.
   No subprocess calls, no network I/O.

2. **Stage 2** -- LLM narrative (Haiku or Sonnet, config-driven).
   Fires only when Stage 1 finds issues above the configured severity
   threshold. Writes a short markdown retro alongside the transcript
   and appends a summary to ``ctx.run_summary``.

Failure of either stage is logged as a warning and the workflow
continues -- analysis is advisory, never fatal.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.config import load_section
from darkfactory.operations.analyze_transcript_detectors import (
    DETECTORS,
    Finding,
)
from darkfactory.utils.claude_code import claude_print
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.utils.secrets import redact
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "analyze_transcript_prompt.md"
_EXCERPT_CAP = 4000  # characters

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warning": 1, "error": 2}
"""Numeric ordering for severity strings. Higher = more severe."""


# ---------- Config helpers ----------


def _load_analysis_config(repo_root: Path) -> dict[str, str]:
    """Return analysis config from ``.darkfactory/config.toml``.

    Reads from ``[workflow.analysis]`` section. Falls back to ``[analysis]``
    for backwards compatibility.

    Config keys:
        commit          -- "true" to stage analysis files for commit (default: false)
        min_severity    -- minimum severity to trigger Stage 2 LLM (default: "warning")
        model_default   -- model for warning-severity runs (default: "haiku")
        model_severe    -- model for error-severity runs (default: "sonnet")
    """
    config_path = repo_root / ".darkfactory" / "config.toml"
    try:
        cfg = load_section(config_path, "analysis")
        return {str(k): str(v) for k, v in cfg.items()}
    except Exception as exc:
        _log.warning("analyze_transcript: failed to read config: %s", exc)
        return {}


# ---------- Transcript discovery ----------


def _find_transcript(ctx: ExecutionContext) -> Path | None:
    """Return the path to the most recent committed transcript, or None."""
    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    if transcript_dir.exists():
        matches = sorted(transcript_dir.glob(f"{ctx.prd.id}-*.jsonl"))
        if matches:
            return matches[-1]
    # Fallback: the harness-level source (outside any worktree)
    src = ctx.repo_root / ".harness-transcripts" / f"{ctx.prd.id}.jsonl"
    if src.exists():
        return src
    return None


# ---------- Transcript parsing ----------


def _parse_transcript(path: Path) -> list[dict[str, Any]]:
    """Parse a transcript JSONL file into a flat list of events.

    Each line in the file is a JSON object representing one event.
    Lines that fail to parse are silently skipped.
    """
    events: list[dict[str, Any]] = []

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass

    return events


# ---------- Stage 1 ----------


def _run_stage1(events: list[dict[str, Any]]) -> list[Finding]:
    """Run every registered detector and aggregate their findings."""
    all_findings: list[Finding] = []
    for name, func in DETECTORS.items():
        try:
            all_findings.extend(func(events))
        except Exception as exc:
            _log.warning("analyze_transcript: detector %r raised: %s", name, exc)
    return all_findings


def _max_severity(findings: list[Finding]) -> str | None:
    """Return the highest-severity string, or None if the list is empty."""
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 0)).severity


# ---------- Stage 2 helpers ----------


def _build_excerpt(events: list[dict[str, Any]], findings: list[Finding]) -> str:
    """Build a capped JSONL excerpt from events near finding line numbers."""
    flagged: set[int] = set()
    for f in findings:
        if f.line is not None:
            for delta in range(-3, 4):
                idx = f.line + delta
                if 0 <= idx < len(events):
                    flagged.add(idx)

    # When no line numbers are recorded, sample head + tail
    if not flagged:
        sample = list(events[:5]) + list(events[-5:])
    else:
        sample = [events[i] for i in sorted(flagged)]

    lines: list[str] = []
    total = 0
    for ev in sample:
        serialized = json.dumps(ev, ensure_ascii=False)
        if total + len(serialized) > _EXCERPT_CAP:
            break
        lines.append(serialized)
        total += len(serialized)

    return "\n".join(lines)


def _format_findings(findings: list[Finding]) -> str:
    """Format findings as a markdown bullet list."""
    if not findings:
        return "(none)"
    parts: list[str] = []
    for f in findings:
        loc = f" (event #{f.line})" if f.line is not None else ""
        parts.append(f"- [{f.severity.upper()}] **{f.category}**: {f.message}{loc}")
    return "\n".join(parts)


def _call_llm(
    prompt: str,
    model: str,
    cwd: Path,
    logger: logging.Logger,
) -> str | None:
    """Call ``claude --print`` for a plain-text narrative response.

    Uses the same ``pnpm dlx @anthropic-ai/claude-code`` plumbing as the
    agent runner but without stream-json formatting -- we just want the
    final text blob. Tools are restricted to ``Read`` only.

    Returns the stripped stdout on success, or ``None`` on any failure.
    """
    try:
        result = claude_print(
            prompt,
            model=model,
            cwd=cwd,
            allowed_tools=["Read"],
            timeout=120,
        )
    except Exception as exc:
        logger.warning("analyze_transcript: LLM subprocess failed: %s", exc)
        return None

    if result.returncode != 0 or not result.stdout.strip():
        logger.warning(
            "analyze_transcript: LLM call returned exit_code=%d", result.returncode
        )
        return None
    return result.stdout.strip()


# ---------- Main builtin ----------


@builtin("analyze_transcript")
def analyze_transcript(ctx: ExecutionContext) -> None:
    """Analyze the agent run transcript for problems and write a retro.

    Stage 1 runs deterministic detectors over the transcript JSONL.
    Stage 2 calls an LLM (Haiku/Sonnet, config-driven) only when Stage 1
    finds issues above the configured severity threshold.

    Writes ``.darkfactory/transcripts/{prd_id}-{ts}.analysis.md`` and
    appends a short summary to ``ctx.run_summary``.

    Missing transcript, scanner failure, or LLM failure all log a warning
    and return cleanly -- analysis is advisory.
    """
    if _log_dry_run(
        ctx,
        f"analyze_transcript: would scan transcript for {ctx.prd.id} and write analysis",
    ):
        return

    # --- Find transcript ---
    transcript_path = _find_transcript(ctx)
    if transcript_path is None:
        ctx.logger.warning(
            "analyze_transcript: no transcript found for %s; skipping", ctx.prd.id
        )
        return

    # --- Stage 1: deterministic scan ---
    try:
        events = _parse_transcript(transcript_path)
        findings = _run_stage1(events)
    except Exception as exc:
        ctx.logger.warning(
            "analyze_transcript: Stage 1 scanner failed: %s; skipping", exc
        )
        return

    # --- Config ---
    analysis_cfg = _load_analysis_config(ctx.repo_root)
    min_severity = analysis_cfg.get("min_severity", "warning")
    model_default = analysis_cfg.get("model_default", "haiku")
    model_severe = analysis_cfg.get("model_severe", "sonnet")

    max_sev = _max_severity(findings)
    min_sev_order = _SEVERITY_ORDER.get(min_severity, 1)
    max_sev_order = _SEVERITY_ORDER.get(max_sev or "info", 0)

    # --- Stage 2: LLM narrative ---
    narrative: str | None = None
    model_used: str | None = None

    if max_sev is not None and max_sev_order >= min_sev_order:
        model_used = model_severe if max_sev == "error" else model_default

        try:
            template = _PROMPT_PATH.read_text(encoding="utf-8")
            excerpt = _build_excerpt(events, findings)
            findings_text = _format_findings(findings)
            prompt = template.replace("{{FINDINGS}}", findings_text).replace(
                "{{TRANSCRIPT_EXCERPT}}", excerpt
            )
            narrative = _call_llm(prompt, model_used, ctx.cwd, ctx.logger)
        except Exception as exc:
            ctx.logger.warning(
                "analyze_transcript: Stage 2 prompt build failed: %s; skipping LLM call",
                exc,
            )

    # --- Build analysis file ---
    findings_md = _format_findings(findings)
    categories = sorted({f.category for f in findings})
    model_note = f" (model: {model_used})" if model_used else ""

    body_parts = [
        f"# Transcript analysis: {ctx.prd.id}",
        "",
        f"**Transcript:** `{transcript_path.name}`",
        f"**Findings:** {len(findings)} ({', '.join(categories) or 'none'})",
        "",
        "## Stage 1 findings",
        "",
        findings_md,
        "",
        f"## Stage 2 narrative{model_note}",
        "",
    ]
    if narrative:
        body_parts.append(narrative)
    elif model_used:
        body_parts.append(
            "*(LLM call attempted but returned no output — check logs for details)*"
        )
    else:
        body_parts.append("*(skipped — no findings above severity threshold)*")

    file_content = "\n".join(body_parts) + "\n"

    # --- Secrets filtering (always on) ---
    redaction = redact(file_content)
    if redaction.redaction_count > 0:
        ctx.logger.info(
            "analyze_transcript: redacted %d secret(s) (%s)",
            redaction.redaction_count,
            ", ".join(redaction.patterns_matched),
        )
        file_content = redaction.text

    # --- Write and stage analysis file ---
    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    try:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        analysis_filename = transcript_path.stem + ".analysis.md"
        analysis_path = transcript_dir / analysis_filename

        analysis_path.write_text(file_content, encoding="utf-8")

        # Only stage for commit if configured — transcripts may contain
        # sensitive information and should not be committed by default.
        commit_analysis = analysis_cfg.get("commit", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        if commit_analysis:
            match git_run("add", "-f", "--", str(analysis_path), cwd=ctx.cwd):
                case Ok():
                    pass
                case GitErr(returncode=code, stderr=err):
                    raise RuntimeError(
                        f"git add -f failed (exit {code}):\n{err}"
                    )
            ctx.logger.info(
                "analyze_transcript: staged %s", analysis_path.relative_to(ctx.cwd)
            )
        else:
            ctx.logger.info(
                "analyze_transcript: wrote %s (not staged — set [analysis] commit = true to include in PR)",
                analysis_path.relative_to(ctx.cwd),
            )
    except Exception as exc:
        ctx.logger.warning(
            "analyze_transcript: failed to write/stage analysis: %s", exc
        )

    # --- Augment ctx.run_summary ---
    summary_lines = [
        "",
        "## Transcript analysis",
        "",
        f"- **Findings:** {len(findings)} issue(s) across {len(categories)} category(s)",
    ]
    for cat in categories:
        cat_count = sum(1 for f in findings if f.category == cat)
        summary_lines.append(f"  - `{cat}`: {cat_count}")
    try:
        rel = (transcript_dir / (transcript_path.stem + ".analysis.md")).relative_to(
            ctx.cwd
        )
        summary_lines.append(f"- **Analysis:** `./{rel}`")
    except ValueError:
        pass

    addendum = "\n".join(summary_lines)
    if ctx.run_summary:
        ctx.run_summary = ctx.run_summary + "\n" + addendum
    else:
        ctx.run_summary = addendum
