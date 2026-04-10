---
id: PRD-560
title: Transcripts should be jsonl files
kind: feature
status: in-progress
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-560.1-rewrite-transcript-assembly-jsonl]]"
  - "[[PRD-560.2-update-commit-transcript-extension]]"
  - "[[PRD-560.3-verify-invoke-parsing]]"
  - "[[PRD-560.4-update-gitignore-patterns]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-09'
tags: []
---

# Transcripts should be jsonl files

## Summary

Transcript files are currently `.log` files containing a few `#`-prefixed metadata lines wrapped around what is otherwise pure JSONL (Claude Code stream-json output). Convert the metadata lines to JSONL as well and rename the files to `.jsonl` so the entire file is valid JSONL and tools can process it without special-casing comment lines.

## Motivation

The transcript body (`result.stdout`) is already JSONL from Claude Code's `--output-format stream-json`. The only non-JSONL content is a handful of `#`-prefixed header/separator lines added by `runner.py` (task name, model, success, exit code, failure reason, and stdout/stderr delimiters). This means:

- Standard JSONL tooling (jq, pandas, etc.) cannot process transcripts without first stripping comment lines.
- The `.log` extension gives no hint about the actual format.
- Downstream code in `invoke.py` already parses line-by-line JSON; it silently skips non-JSON lines, so the metadata is effectively invisible to programmatic consumers.

Switching to pure JSONL makes transcripts a first-class structured format that any JSON-aware tool can consume directly.

## Requirements

### Functional

1. Metadata currently written as `#`-prefixed comment lines in `runner.py:_run_agent` must be emitted as a single JSONL line with `"type": "darkfactory_metadata"` at the top of the file, containing fields: `task`, `model`, `success`, `exit_code`, `failure_reason`.
2. The `# ---- stdout ----` and `# ---- stderr ----` separator lines must be removed. Instead, emit a `{"type": "darkfactory_section", "section": "stdout"}` line before stdout content and `{"type": "darkfactory_section", "section": "stderr"}` before stderr content.
3. Transcript files must use the `.jsonl` extension instead of `.log` — both in the transient location (`.harness-transcripts/{prd_id}.jsonl`) and the committed location (`.darkfactory/transcripts/{prd_id}-{timestamp}.jsonl`).
4. `commit_transcript.py` must look for the new `.jsonl` filename when copying from the transient location.
5. Stderr content (typically plain text, not JSON) must be wrapped in a JSONL line: `{"type": "darkfactory_stderr", "text": "..."}` (one line per stderr line, or a single entry with the full stderr block).

### Non-Functional

1. Existing `.log` transcripts already committed in repos should not break anything — but no migration of old files is required.
2. Any code that parses transcripts (e.g., `invoke.py:_find_terminal_result`) should continue to work, either by naturally skipping the new envelope lines or with minor updates.

## Technical Approach

**Affected files:**

- `src/darkfactory/runner.py` (~lines 356-377) — rewrite the transcript assembly block to emit JSONL lines instead of `#`-prefixed comments.
- `src/darkfactory/builtins/commit_transcript.py` (~lines 36-58) — change `.log` references to `.jsonl`.
- `src/darkfactory/invoke.py` — verify `_find_terminal_result` and `_parse_sentinels` still work (they parse JSON lines and skip non-JSON; the new envelope lines are JSON so confirm they don't interfere with sentinel detection).

**JSONL structure of a transcript file:**

```jsonl
{"type": "darkfactory_metadata", "task": "implement", "model": "sonnet", "success": true, "exit_code": 0, "failure_reason": null}
{"type": "darkfactory_section", "section": "stdout"}
{"type":"system","subtype":"init","cwd":"...","session_id":"..."}
{"type":"assistant","message":{...}}
...
{"type": "darkfactory_section", "section": "stderr"}
{"type": "darkfactory_stderr", "text": "Warning: something"}
```

## Acceptance Criteria

- [ ] AC-1: Transcripts written by `runner.py` are valid JSONL (every line parses as JSON).
- [ ] AC-2: Transcript files use `.jsonl` extension in both transient and committed locations.
- [ ] AC-3: `commit_transcript` builtin correctly finds and copies `.jsonl` files.
- [ ] AC-4: Metadata (task, model, success, exit_code, failure_reason) is present as a `darkfactory_metadata` JSONL line.
- [ ] AC-5: Existing transcript parsing in `invoke.py` continues to function correctly.
- [ ] AC-6: Stderr content is wrapped in JSONL rather than written as raw text.

## Open Questions

- OPEN: Should we emit one `darkfactory_stderr` line per stderr line, or a single line with the full stderr block? Single line is simpler but could be very long. SINGLE LINE FOR NOW
- OPEN: Should `.gitignore` patterns referencing `.log` transcripts be updated? YES THEY SHOULD

## References

- `src/darkfactory/runner.py:356-377` — current transcript writing
- `src/darkfactory/builtins/commit_transcript.py:36-58` — transcript commit logic
- `src/darkfactory/invoke.py:104-343` — transcript parsing
