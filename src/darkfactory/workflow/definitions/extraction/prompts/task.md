# Task: Execute {{PRD_ID}} — {{PRD_TITLE}}

You are inside the pumice worktree at `{{WORKTREE_PATH}}` on branch
`{{BRANCH_NAME}}`. The PRD's actual work happens in a separate target
repository — read the PRD to find which one and where it lives on disk.

## Steps

### 1. Read the PRD

Read `{{PRD_PATH}}` end-to-end. Note:

- Which target repo this PRD touches (path on disk).
- The Technical Approach — exact commands, file contents, sequencing.
- The Acceptance Criteria — what you must verify before declaring done.
- The parent epic and sibling PRDs in the References section for context.

### 2. Execute in the target repo

Carry out the Technical Approach. Typical operations:

- `git clone` or `cd` into the target repo.
- Run extraction tooling (`git filter-repo`, etc.).
- Create or edit scaffolding files (`pyproject.toml`, `mise.toml`,
  `.gitignore`, etc.).
- Run target-repo verification (`mise install`, `uv sync`, `pytest`,
  `mypy`, `git log`).

Stop and report `PRD_EXECUTE_FAILED` if a step in the Technical
Approach can't be completed and there's no obvious recovery.

### 3. Verify Acceptance Criteria

Walk every AC in the PRD and confirm it. For each one print:

```
AC-1: PASS — <one-line evidence>
AC-2: PASS — <one-line evidence>
```

If any AC fails, report `PRD_EXECUTE_FAILED` with the failing AC.

### 4. Commit pumice-side changes (if any)

The harness has already committed the status transition. If you made
*additional* pumice-side changes (rare for extraction PRDs — usually
none), stage and commit them now with a conventional-commits message:

- `chore(prd): {{PRD_ID}} <one-line summary>`

Subject must be lowercase after the scope. Do not push, branch, or
open a PR — the harness handles those after you return.

### 5. Emit the sentinel

Your final line must be exactly one of:

- `PRD_EXECUTE_OK: {{PRD_ID}}`
- `PRD_EXECUTE_FAILED: <reason>`
