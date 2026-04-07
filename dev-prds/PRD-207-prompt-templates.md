---
id: "PRD-207"
title: "Prompt Template Loader"
kind: task
status: review
priority: high
effort: xs
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
blocks:
  - "[[PRD-210-runner]]"
impacts:
  - tools/prd-harness/src/prd_harness/templates.py
  - tools/prd-harness/tests/test_templates.py
workflow: null
target_version: null
created: 2026-04-07
updated: 2026-04-08
tags:
  - harness
  - templates
  - prompts
---

# Prompt Template Loader

## Summary

Load prompt files relative to a workflow's directory, concatenate them, and substitute `{{PRD_ID}}` / `{{PRD_TITLE}}` / `{{PRD_PATH}}` / `{{BRANCH_NAME}}` / `{{WORKTREE_PATH}}` / `{{CHECK_OUTPUT}}` placeholders. Pure, no I/O beyond reading the files.

## Requirements

1. `load_prompt_files(workflow_dir, paths) -> str` — concatenate file contents with `\n\n` separators
2. `substitute_placeholders(template, context) -> str` — replace `{{VAR}}` tokens with values from `context` dict
3. `compose_prompt(workflow, prompts, execution_context, extras=None) -> str` — full pipeline: load files, substitute placeholders from ExecutionContext + optional extras (e.g. `CHECK_OUTPUT` for retry)
4. Missing files raise `FileNotFoundError` with workflow name in the message
5. Unknown placeholders are left as-is (not an error) — simplifies incremental template evolution

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/templates.py`

```python
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

def load_prompt_files(workflow_dir, paths):
    return "\n\n".join((workflow_dir / p).read_text() for p in paths)

def substitute_placeholders(template, context):
    def replace(match):
        key = match.group(1)
        return str(context.get(key, match.group(0)))  # leave unknown alone
    return PLACEHOLDER_RE.sub(replace, template)

def compose_prompt(workflow, prompts, execution_context, extras=None):
    raw = load_prompt_files(workflow.workflow_dir, prompts)
    ctx = {
        "PRD_ID": execution_context.prd.id,
        "PRD_TITLE": execution_context.prd.title,
        "PRD_PATH": str(execution_context.prd.path),
        "BRANCH_NAME": execution_context.branch_name,
        "WORKTREE_PATH": str(execution_context.worktree_path or ""),
        "BASE_REF": execution_context.base_ref,
    }
    if extras:
        ctx.update(extras)
    return substitute_placeholders(raw, ctx)
```

**New file**: `tools/prd-harness/tests/test_templates.py` — fixture workflow dir with a role.md, verify substitution, missing file error, unknown placeholders preserved.

## Acceptance Criteria

- [ ] AC-1: `load_prompt_files` concatenates multiple files with blank lines between
- [ ] AC-2: `substitute_placeholders` replaces known `{{VAR}}` tokens
- [ ] AC-3: Unknown placeholders are left unchanged (not an error)
- [ ] AC-4: Missing prompt file raises `FileNotFoundError`
- [ ] AC-5: `compose_prompt` integrates all three steps
- [ ] AC-6: `mypy --strict` passes
- [ ] AC-7: `pytest tests/test_templates.py` passes
