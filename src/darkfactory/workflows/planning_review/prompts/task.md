# Task: Review decomposition of {{PRD_ID}} — {{PRD_TITLE}}

You are working inside the git worktree at `{{WORKTREE_PATH}}` on
branch `{{BRANCH_NAME}}`. The branch was created from `{{BASE_REF}}`
and is already checked out.

## Steps

### 1. Read the parent PRD

Read `{{PRD_PATH}}` from start to finish. Pay particular attention to:

- **Requirements** — the functional constraints and deliverables.
- **Technical Approach** — file paths, function signatures, and
  implementation patterns.
- **Acceptance Criteria** — these inform what each child task must
  deliver.

If the PRD references other PRDs or design docs, read those too for
context.

### 2. List existing children

Glob `.darkfactory/prds/{{PRD_ID}}.*.md` to find all existing
child PRDs.

### 3. Read every existing child

Read each child PRD end-to-end. Note:
- What requirement(s) each child addresses
- The child's scope and boundaries
- Any obvious gaps or overlaps between children

### 4. Build a coverage map

For each requirement in the parent PRD, determine which existing
child (if any) covers it. Organize this as a matrix:

| Parent Requirement | Covered By | Status |
|---|---|---|
| Req 1: ... | PRD-X.1 | covered |
| Req 2: ... | PRD-X.3 | partial |
| Req 3: ... | (none) | **gap** |

### 5. Decide: gaps or complete?

**If no gaps**: skip to step 9.

**If gaps exist**: continue to step 6.

### 6. Write new child PRD files

For each gap, use `Write` to create a new file in `.darkfactory/prds/`:

- Filename: `PRD-{parent_number}.{index}-{slug}.md`
- Pick the next unused sibling index by globbing existing children
- Include all required frontmatter fields
- Write substantive body sections (Summary, Requirements, Technical
  Approach with file paths, Acceptance Criteria)

### 7. Update the parent PRD

Read `{{PRD_PATH}}` again, then write it back with the `blocks:`
field updated to include wikilinks to **all** children (existing +
new). Preserve everything else exactly as-is.

### 8. Validate

Run `uv run prd validate` and fix any errors. Repeat until
validation passes cleanly.

### 9. Stage your changes

```bash
git add .darkfactory/prds/
git status
```

### 10. Report

Print a summary:

**If gaps were found and filled:**
- How many gaps were identified
- How many new child PRDs were created
- The coverage map showing existing + new children

**If no gaps:**
- Confirmation that all requirements are covered
- The coverage map for reference

### 11. Emit the sentinel

**If gaps were filled**, your final lines must be:

```
created: PRD-X.5, PRD-X.6
PRD_EXECUTE_OK: {{PRD_ID}}
```

**If no gaps were found**, your final lines must be:

```
complete: no gaps found
PRD_EXECUTE_OK: {{PRD_ID}}
```

The sentinel **must be the very last line** of your output — the
harness parses only the final line to determine the task outcome.
