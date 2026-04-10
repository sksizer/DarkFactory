---
id: "PRD-604"
title: "JSONL transcript validation"
kind: task
status: blocked
priority: medium
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - "src/darkfactory/runner.py"
workflow: null
target_version: null
created: '2026-04-09'
updated: '2026-04-09'
tags:
  - harness
  - quality
---

# JSONL transcript validation

## Problem

PR #145 (transcripts as JSONL) has a gap: `_write_transcript` appends stdout lines verbatim, but `InvokeResult.stdout` is not guaranteed to be JSONL. For example, `invoke_claude(dry_run=True)` returns plain text, and some test/mock paths return plain text. This means the resulting `.jsonl` file can contain non-JSON lines, violating the "every line parses as JSON" JSONL contract (AC-1).

Additionally, no tests verify that emitted transcripts are valid JSONL.

## Requirements

1. Validate each stdout line with `json.loads()` before writing to transcript.
2. Wrap non-JSON lines (blank lines, plain text) in a JSON object (e.g., `{"type": "darkfactory_stdout_text", "text": "..."}`).
3. Add tests asserting that the emitted transcript is valid JSONL (`json.loads` succeeds on every line), including the dry-run/plain-text stdout case.

## Acceptance criteria

- [ ] Every line in emitted `.jsonl` transcripts is valid JSON
- [ ] Non-JSON stdout lines are wrapped in a `darkfactory_stdout_text` JSON envelope
- [ ] Test exists verifying JSONL validity including dry-run case
