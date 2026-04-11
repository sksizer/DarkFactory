---
id: "PRD-603"
title: "Transcript analysis robustness and error handling"
kind: task
status: blocked
priority: medium
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - "src/darkfactory/builtins/analyze_transcript.py"
  - "src/darkfactory/builtins/analyze_transcript_detectors.py"
workflow: null
target_version: null
created: '2026-04-09'
updated: '2026-04-09'
tags:
  - harness
  - quality
---

# Transcript analysis robustness and error handling

## Problem

PR #143 and #144 review comments identified several robustness gaps in the transcript analysis module:

### Error handling (PR #144)
1. `parse_transcript()` can raise on I/O or encoding errors — not caught, would crash workflow
2. `_load_analysis_config()` doesn't handle TOML parse errors or non-table `analysis` values
3. Analysis file write + `git add` not protected — `check=True` will abort workflow on failure
4. Missing transcript logs at INFO — AC-7 says it should be WARNING
5. `append_summary` uses absolute paths — should use repo-relative paths for PR bodies

### Detector logic (PR #143)
6. `detect_repeated_edit` only flags consecutive calls when tool name AND path match — misses Edit→Write and Write→Edit on the same file, which the docstring says should be caught
7. Missing tests for Edit→Write cross-detection

### Minor (PR #143)
8. Unused `from typing import Any` import in test file

## Requirements

1. Wrap `parse_transcript()` call in try/except, log warning and return cleanly on failure.
2. Add error handling to `_load_analysis_config()` for TOML errors, fall back to defaults.
3. Wrap analysis write + `git add` in try/except, log warning and continue.
4. Change missing-transcript log from INFO to WARNING.
5. Use `analysis_path.relative_to(ctx.cwd)` in summary output.
6. Fix `detect_repeated_edit` to track by file path for Edit/Write tools (not by `(tool_name, path)` tuple).
7. Add tests for Edit→Write and Write→Edit cross-detection.

## Acceptance criteria

- [ ] Workflow completes cleanly when transcript file is missing, malformed, or unreadable
- [ ] Workflow completes cleanly when analysis write or git-add fails
- [ ] Missing transcript logs at WARNING level
- [ ] Edit→Write on same file is flagged as repeated edit
- [ ] Summary uses repo-relative path
