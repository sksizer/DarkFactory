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

### 3. Run tests and lint

Run the tests:

```bash
just test
```

And the lint/format checks:

```bash
just lint format-check
```

Fix any failures. If tests that were passing before start failing, you
broke something — investigate and fix, don't paper over.

### 4. Commit

Stage your changes and commit with a conventional-commits message:

- `feat(prd-harness): {{PRD_ID}} <one-line summary>` for new features
- `fix(prd-harness): {{PRD_ID}} <one-line summary>` for bug fixes
- `chore(prd-harness): {{PRD_ID}} <one-line summary>` otherwise

The subject line must be lowercase after the scope (commitlint rule).
Include a body explaining what changed and why. Reference the PRD
filename in the body. Do not bypass commit hooks.

**Do not** push, branch, or open a PR — the harness will handle those
steps after you return.

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

- `PRD_EXECUTE_OK: {{PRD_ID}}` — everything passed, commit made.
- `PRD_EXECUTE_FAILED: <reason>` — you could not complete the task.

The harness reads this line to decide the next step.
