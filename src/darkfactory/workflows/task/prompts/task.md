# Task: Implement {{PRD_ID}} — {{PRD_TITLE}}

You are working inside the git worktree at `{{WORKTREE_PATH}}` on
branch `{{BRANCH_NAME}}`. The branch was created from `{{BASE_REF}}`
and is already checked out.

## Steps

### 1. Read the PRD

Read `{{PRD_PATH}}` from start to finish. Pay particular attention to:

- **Requirements** — the functional and non-functional constraints
  you must satisfy.
- **Technical Approach** — file paths, function signatures, and
  implementation patterns to follow.
- **Acceptance Criteria** — the checklist you must make pass.

If the PRD references other files (other PRDs, source modules, design
docs), read those too before starting.

### 2. Implement

Write the code specified in the Technical Approach. Prefer the exact
file paths and function signatures the PRD lists when it's explicit;
use judgment when it's not. Follow the project's existing patterns —
look at nearby files for style cues (imports, naming, docstrings,
type annotations).

### 3. Run tests

Run the tests to make sure your changes don't break anything:

```bash
just test
```

Fix any failing tests. If tests that were passing before start failing, you
broke something — investigate and fix, don't paper over.

**Do not run these tools yourself:**
- `ruff format` or `just format-check` — the harness auto-formats after
  you finish, so formatting drift is not your concern.
- `mypy` or `just typecheck` — the harness runs mypy after formatting. If
  mypy flags a real type bug, the harness will bring you back with the error
  message; fix that one thing and return.

The harness handles format and typecheck deterministically so you can focus
on logic correctness.

### 4. Stage your changes

Run `git add` for the files you modified or created so the harness's
commit builtin can see them:

```bash
git add -A
git status
git diff --cached
```

You may commit incrementally as you work using conventional-commits
messages (e.g. `git commit -m "feat: ..."`). The harness makes
additional boundary commits after you return regardless, so committing
is optional but encouraged for logical checkpoints.

You must not push, branch, or open a PR — the harness handles all of those.

### 5. Report

Print a brief summary of what you did, then for each acceptance
criterion in the PRD print one line:

```
AC-1: PASS — <one-line evidence>
AC-2: PASS — <one-line evidence>
AC-3: FAIL — <reason>
```

### 6. Emit the sentinel

Your final line must be exactly one of:

- `PRD_EXECUTE_OK: {{PRD_ID}}` — everything passed, changes are staged.
- `PRD_EXECUTE_FAILED: <reason>` — you could not complete the task.

The harness reads this line to decide the next step.
