---
id: "PRD-208"
title: "Claude Code Subprocess Wrapper"
kind: task
status: done
priority: high
effort: s
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
blocks:
  - "[[PRD-210-runner]]"
impacts:
  - tools/prd-harness/src/prd_harness/invoke.py
  - tools/prd-harness/tests/test_invoke.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - agent
  - claude-code
---

# Claude Code Subprocess Wrapper

## Summary

Wrap `claude --print` (via `pnpm dlx @anthropic-ai/claude-code`) as a subprocess with prompt-via-stdin, restricted tool allowlist, model selection, and sentinel-based success detection. Returns an `InvokeResult` with the full output, exit code, and success/failure flags.

## Requirements

1. `InvokeResult` dataclass: `stdout: str`, `stderr: str`, `exit_code: int`, `success: bool`, `failure_reason: str | None`
2. `invoke_claude(prompt, tools, model, cwd, sentinel_success, sentinel_failure, timeout_seconds=600) -> InvokeResult` — runs the subprocess
3. Uses `subprocess.run` with `input=prompt`, `text=True`, `cwd=...`, `timeout=...`
4. Parses stdout for the sentinel lines:
   - `PRD_EXECUTE_OK: <id>` anywhere in output → success=True
   - `PRD_EXECUTE_FAILED: <reason>` → success=False, failure_reason=extracted reason
5. Timeout → `InvokeResult(..., success=False, failure_reason="timeout after Ns")`
6. `capability_to_model(capability: str) -> str` — maps trivial/simple/moderate/complex to haiku/sonnet/sonnet/opus

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/invoke.py`

```python
CAPABILITY_MODELS = {
    "trivial": "haiku",
    "simple": "sonnet",
    "moderate": "sonnet",
    "complex": "opus",
}

def capability_to_model(capability):
    return CAPABILITY_MODELS.get(capability, "sonnet")

def invoke_claude(prompt, tools, model, cwd, ...):
    cmd = [
        "pnpm", "dlx", "@anthropic-ai/claude-code",
        "--print",
        "--model", model,
        "--allowed-tools", ",".join(tools),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return InvokeResult(..., success=False, failure_reason=f"timeout after {timeout_seconds}s")
    # Parse sentinels from stdout
    ...
```

**New file**: `tools/prd-harness/tests/test_invoke.py`

Mock `subprocess.run` via `unittest.mock.patch`. Test: success sentinel detected, failure sentinel detected, timeout handled, capability mapping.

## Acceptance Criteria

- [ ] AC-1: `InvokeResult` dataclass with all fields
- [ ] AC-2: `invoke_claude` builds the correct subprocess command
- [ ] AC-3: Success sentinel detected → `success=True`
- [ ] AC-4: Failure sentinel detected → `success=False` + reason extracted
- [ ] AC-5: Timeout → `success=False` with "timeout" in reason
- [ ] AC-6: `capability_to_model` returns correct model per tier
- [ ] AC-7: `mypy --strict` passes
- [ ] AC-8: `pytest tests/test_invoke.py` passes (with mocked subprocess)
