"""Built-in: analyze_transcript — Stage 1 + Stage 2 transcript analysis.

Orchestrates the two-stage transcript analysis pipeline:

- **Stage 1**: load the JSONL transcript, parse events, run all registered
  detectors, collect findings.
- **Stage 2**: if any finding meets the severity threshold (from config),
  invoke ``claude --print`` with the prompt template to produce a narrative.

Writes the result to ``.darkfactory/transcripts/{prd_id}-{ts}.analysis.md``
and stages it with ``git add``. Appends a short section to
``ctx.run_summary``.

All failure modes (missing transcript, detector crash, LLM failure) are
handled by logging a warning and returning cleanly so the workflow can
continue.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

from darkfactory.builtins._registry import builtin
from darkfactory.builtins.analyze_transcript_detectors import DETECTORS, Finding
from darkfactory.workflow import ExecutionContext

logger = logging.getLogger(__name__)

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warning": 1, "error": 2}
_DEFAULT_MIN_SEVERITY = "warning"
_DEFAULT_MODEL_DEFAULT = "haiku"
_DEFAULT_MODEL_SEVERE = "sonnet"
_PROMPT_TEMPLATE_PATH = Path(__file__).parent / "analyze_transcript_prompt.md"

# ~4k tokens at 4 chars/token
_EXCERPT_MAX_CHARS = 16_000


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_analysis_config(ctx: ExecutionContext) -> dict[str, str]:
    """Load [analysis] section from .darkfactory/config.toml with defaults."""
    config_path = ctx.repo_root / ".darkfactory" / "config.toml"
    analysis_data: dict[str, object] = {}
    if config_path.is_file():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        analysis_data = raw.get("analysis", {})
    return {
        "min_severity": str(analysis_data.get("min_severity", _DEFAULT_MIN_SEVERITY)),
        "model_default": str(
            analysis_data.get("model_default", _DEFAULT_MODEL_DEFAULT)
        ),
        "model_severe": str(analysis_data.get("model_severe", _DEFAULT_MODEL_SEVERE)),
    }


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------


def find_transcript(ctx: ExecutionContext) -> Path | None:
    """Locate the agent transcript JSONL file, mirroring commit_transcript pattern."""
    src = ctx.repo_root / ".harness-transcripts" / f"{ctx.prd.id}.jsonl"
    if src.exists():
        return src
    return None


def parse_transcript(path: Path) -> list[dict[str, object]]:
    """Read a JSONL transcript file, returning a list of event dicts."""
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSONL line: %r", line[:80])
    return events


def run_detectors(events: list[dict[str, object]]) -> list[Finding]:
    """Iterate all registered detectors, isolating individual failures."""
    findings: list[Finding] = []
    for name, fn in DETECTORS.items():
        try:
            findings.extend(fn(events))
        except Exception:
            logger.warning("Detector %r crashed; skipping", name, exc_info=True)
    return findings


def exceeds_threshold(findings: list[Finding], analysis_config: dict[str, str]) -> bool:
    """Return True if any finding meets or exceeds min_severity from config."""
    threshold = _SEVERITY_ORDER.get(analysis_config["min_severity"], 1)
    return any(_SEVERITY_ORDER.get(f.severity, 0) >= threshold for f in findings)


# ---------------------------------------------------------------------------
# Stage 2 helpers
# ---------------------------------------------------------------------------


def _format_findings(findings: list[Finding]) -> str:
    """Format findings as a markdown bullet list."""
    if not findings:
        return "No findings."
    lines = []
    for f in findings:
        line_info = f" (line {f.line})" if f.line is not None else ""
        lines.append(f"- [{f.severity.upper()}] {f.category}: {f.message}{line_info}")
    return "\n".join(lines)


def _build_excerpt(findings: list[Finding], events: list[dict[str, object]]) -> str:
    """Build a transcript excerpt: events tagged by findings ±3, capped at ~4k tokens."""
    if not events:
        return "No events."

    tagged: set[int] = set()
    for f in findings:
        if f.line is not None:
            idx = f.line - 1  # convert 1-based line to 0-based index
            for i in range(max(0, idx - 3), min(len(events), idx + 4)):
                tagged.add(i)

    if not tagged:
        # No line info: include first and last 10 events for context
        head = list(range(min(10, len(events))))
        tail = list(range(max(0, len(events) - 10), len(events)))
        tagged = set(head + tail)

    lines = []
    for i in sorted(tagged):
        try:
            serialised = json.dumps(events[i], ensure_ascii=False)
        except Exception:
            serialised = str(events[i])
        lines.append(f"[{i + 1}] {serialised}")

    excerpt = "\n".join(lines)
    if len(excerpt) > _EXCERPT_MAX_CHARS:
        excerpt = excerpt[:_EXCERPT_MAX_CHARS] + "\n... [truncated]"
    return excerpt


def invoke_llm(
    findings: list[Finding],
    events: list[dict[str, object]],
    analysis_config: dict[str, str],
) -> str:
    """Load prompt template, fill placeholders, select model, call claude --print."""
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{FINDINGS}}", _format_findings(findings)).replace(
        "{{TRANSCRIPT_EXCERPT}}", _build_excerpt(findings, events)
    )

    max_sev = max(
        (_SEVERITY_ORDER.get(f.severity, 0) for f in findings),
        default=0,
    )
    model = (
        analysis_config["model_severe"]
        if max_sev >= _SEVERITY_ORDER.get("error", 2)
        else analysis_config["model_default"]
    )

    result = subprocess.run(
        ["claude", "--print", "--model", model],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def write_analysis(
    ctx: ExecutionContext,
    findings: list[Finding],
    narrative: str | None,
) -> Path:
    """Format and write the .analysis.md file, returning its path."""
    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    analysis_path = transcript_dir / f"{ctx.prd.id}-{timestamp}.analysis.md"

    parts = [
        f"# Transcript Analysis: {ctx.prd.id}",
        "",
        f"**Generated:** {timestamp}",
        f"**Findings:** {len(findings)}",
        "",
        "## Stage 1 Findings",
        "",
        _format_findings(findings),
        "",
    ]

    if narrative:
        parts += [
            "## Stage 2 Narrative",
            "",
            narrative,
            "",
        ]

    analysis_path.write_text("\n".join(parts), encoding="utf-8")
    return analysis_path


def append_summary(
    ctx: ExecutionContext,
    findings: list[Finding],
    analysis_path: Path | None,
) -> None:
    """Append a short analysis section to ctx.run_summary."""
    categories = sorted({f.category for f in findings})
    lines = [
        "",
        "## Transcript Analysis",
        "",
    ]
    if findings:
        lines.append(f"- **Findings:** {len(findings)}")
        if categories:
            lines.append(f"- **Categories:** {', '.join(categories)}")
    else:
        lines.append("- No findings above threshold.")

    if analysis_path:
        lines.append(f"- **Analysis file:** {analysis_path}")

    section = "\n".join(lines)
    ctx.run_summary = (ctx.run_summary or "") + section


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@builtin("analyze_transcript")
def analyze_transcript(ctx: ExecutionContext, **kwargs: object) -> None:
    """Orchestrate Stage 1 (detector scan) and Stage 2 (LLM narrative) analysis."""
    # 1. Locate transcript file
    transcript_path = find_transcript(ctx)
    if not transcript_path:
        logger.info("No transcript found, skipping analysis")
        return

    # 2. Parse JSONL events
    events = parse_transcript(transcript_path)

    # 3. Stage 1 — run detectors
    findings = run_detectors(events)

    # 4. Load analysis config
    analysis_config = _load_analysis_config(ctx)

    # 5. Check severity threshold
    if not exceeds_threshold(findings, analysis_config):
        logger.info("No findings above threshold, skipping Stage 2")
        append_summary(ctx, findings, analysis_path=None)
        return

    # 6. Dry-run check
    if ctx.dry_run:
        logger.info("Dry run: would invoke LLM and write analysis")
        return

    # 7. Stage 2 — LLM narrative
    try:
        narrative = invoke_llm(findings, events, analysis_config)
    except Exception:
        logger.warning("LLM call failed, skipping narrative", exc_info=True)
        narrative = None

    # 8. Write analysis file
    analysis_path = write_analysis(ctx, findings, narrative)

    # 9. Stage with git add
    subprocess.run(["git", "add", str(analysis_path)], cwd=str(ctx.cwd), check=True)

    # 10. Augment run summary
    append_summary(ctx, findings, analysis_path)
