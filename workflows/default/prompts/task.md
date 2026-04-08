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

### 4. Stage your changes

Run `git add` for the files you modified or created so the harness's
commit builtin can see them:

```bash
git add -A
git status
git diff --cached
```

**Do not run `git commit`.** The harness commits immediately after
you return — it owns commit-message authoring and history shape, and
`git commit` is intentionally outside your tool allowlist. If you try
to commit, the run will fail.

You also must not push, branch, or open a PR — the harness handles
all of those.

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
