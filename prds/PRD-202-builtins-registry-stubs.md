---
id: "PRD-202"
title: "Builtins Registry + Stub Primitives"
kind: task
status: done
priority: high
effort: xs
capability: trivial
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
blocks:
  - "[[PRD-205-default-workflow]]"
  - "[[PRD-209-real-builtins]]"
  - "[[PRD-210-runner]]"
impacts:
  - src/darkfactory/builtins.py
  - tests/test_builtins.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - builtins
---

# Builtins Registry + Stub Primitives

## Summary

Create the builtin task registry and register stub implementations for each primitive. Stubs raise `NotImplementedError` — real implementations land in PRD-209. The registry itself is functional so downstream code (loader, assign, runner dry-run) can reference builtins by name.

## Requirements

1. `BUILTINS: dict[str, BuiltInFunc]` module-level registry
2. `@builtin("name")` decorator that registers a function and rejects duplicate names
3. Stub implementations (raise `NotImplementedError`) for: `ensure_worktree`, `set_status`, `commit`, `push_branch`, `create_pr`, `cleanup_worktree`
4. `BuiltInFunc = Callable[..., None]` type alias

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/builtins.py`

```python
BUILTINS: dict[str, BuiltInFunc] = {}

def builtin(name: str) -> Callable[[BuiltInFunc], BuiltInFunc]:
    def decorator(func):
        if name in BUILTINS:
            raise ValueError(f"duplicate builtin: {name}")
        BUILTINS[name] = func
        return func
    return decorator

@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None:
    raise NotImplementedError("ensure_worktree — implemented in PRD-209")

# ... same pattern for set_status, commit, push_branch, create_pr, cleanup_worktree
```

**New file**: `tools/prd-harness/tests/test_builtins.py`

Test: decorator registers, duplicate raises, all 6 names present in BUILTINS, each stub raises NotImplementedError when called.

## Acceptance Criteria

- [ ] AC-1: All 6 builtin names registered in `BUILTINS` dict
- [ ] AC-2: `@builtin("foo")` duplicate raises `ValueError`
- [ ] AC-3: Each stub raises `NotImplementedError` when called
- [ ] AC-4: `mypy --strict` passes
- [ ] AC-5: `pytest tests/test_builtins.py` passes
