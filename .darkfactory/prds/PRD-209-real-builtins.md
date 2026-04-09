---
id: "PRD-209"
title: "Real Builtin Implementations"
kind: task
status: done
priority: high
effort: m
capability: moderate
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-202-builtins-registry-stubs]]"
blocks:
  - "[[PRD-211-plan-run-cli]]"
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
  - git
---

# Real Builtin Implementations

## Summary

Replace the stub implementations in `builtins.py` with real subprocess-based git and `gh` operations: worktree creation, commits, branch push, PR creation, cleanup. Uses `subprocess.run` for all shell commands with explicit argv lists (no shell=True).

## Requirements

1. **`ensure_worktree(ctx)`** — `git worktree add -b <branch> .worktrees/<prd_id>-<slug> <base_ref>`. If `.worktrees/<prd_id>-<slug>` already exists, reuse it (resume). Sets `ctx.worktree_path` and `ctx.cwd`.
2. **`set_status(ctx, to=...)`** — delegates to `prd.set_status(ctx.prd, to)` (already implemented)
3. **`commit(ctx, message=...)`** — `git add -A && git commit -m <formatted_message>` inside `ctx.cwd`. Message supports `{prd_id}`, etc. via `ctx.format_string`. If there's nothing to commit, log and skip (no error).
4. **`push_branch(ctx)`** — `git push -u origin <branch>` inside `ctx.cwd`
5. **`create_pr(ctx)`** — `gh pr create --base <base_ref> --title "<id>: <title>" --body-file <temp>`. Body generated from PRD acceptance criteria + link. Captures the PR URL from stdout and sets `ctx.pr_url`.
6. **`cleanup_worktree(ctx)`** — `git worktree remove <worktree_path>` (idempotent)
7. All builtins respect `ctx.dry_run`: log what they WOULD do, don't actually run
8. Each subprocess call uses a `run_git(ctx, args)` / `run_gh(ctx, args)` helper that centralizes cwd, check, capture, dry-run handling

## Technical Approach

**Modify**: `tools/prd-harness/src/prd_harness/builtins.py`

Replace each stub with a real implementation. Add internal helpers:

```python
def _run(ctx, cmd, check=True, capture=False):
    if ctx.dry_run:
        ctx.logger.info(f"[dry-run] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(cmd, cwd=ctx.cwd, check=check, capture_output=capture, text=True)

def _pr_body(prd):
    lines = [f"# {prd.id}: {prd.title}", "", "Implements [[{prd.id}]]", "", "## Acceptance criteria", ""]
    # extract ACs from prd.body via regex...
    return "\n".join(lines)
```

**Modify**: `tools/prd-harness/tests/test_builtins.py`

Add fixtures using `tmp_path` + `subprocess.run("git init")`. Test:
- `ensure_worktree` creates a worktree directory
- `commit` adds and commits files
- Dry-run mode doesn't touch anything
- `push_branch` and `create_pr` are tested via mocked subprocess

## Acceptance Criteria

- [ ] AC-1: `ensure_worktree` creates `.worktrees/<id>-<slug>/` with correct branch
- [ ] AC-2: `commit` stages and commits (or no-ops gracefully on empty diff)
- [ ] AC-3: `push_branch` and `create_pr` use mocked subprocess in tests
- [ ] AC-4: Dry-run mode never invokes real git/gh commands
- [ ] AC-5: `cleanup_worktree` is idempotent (safe to call twice)
- [ ] AC-6: `mypy --strict` passes
- [ ] AC-7: `pytest tests/test_builtins.py` passes (extended tests)
