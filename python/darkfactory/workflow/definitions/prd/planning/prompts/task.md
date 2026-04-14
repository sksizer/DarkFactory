# Task: Decompose {{PRD_ID}} — {{PRD_TITLE}}

You are working inside the git worktree at `{{WORKTREE_PATH}}` on
branch `{{BRANCH_NAME}}`. The branch was created from `{{BASE_REF}}`
and is already checked out.

## Steps

### 1. Read the parent PRD

Read `{{PRD_PATH}}` from start to finish. Pay particular attention to:

- **Requirements** — the functional constraints and deliverables.
- **Technical Approach** — file paths, function signatures, and
  implementation patterns. These are your primary decomposition seams.
- **Acceptance Criteria** — these inform what each child task must
  deliver.

If the PRD references other PRDs or design docs, read those too for
context.

### 2. Study the PRD format

Read `.darkfactory/prds/_template.md` if it exists. If not, find an existing
well-formed `kind: task` PRD in the `.darkfactory/prds/` directory and use it as
a reference for the format.

### 3. Survey existing PRDs

Glob `.darkfactory/prds/PRD-*.md` to see what PRDs already exist. Note the ID
numbering scheme so your new children don't collide.

### 4. Identify decomposition seams

Based on the parent PRD's structure, identify the natural task
boundaries. Consider:

- What needs to happen first (schema, data model, API contracts)?
- What can be parallelized?
- What has clear interface boundaries?

### 5. Plan the dependency graph

Before writing any files, plan the ordering:

- Which tasks must come before others?
- Which can run in parallel?
- What's the critical path?

### 6. Write the child PRD files

For each task, use `Write` to create a new file in `.darkfactory/prds/`:

- Filename: `PRD-{parent_number}.{index}-{slug}.md`
- Include all required frontmatter fields
- Write substantive body sections (Summary, Requirements, Technical
  Approach with file paths, Acceptance Criteria)

### 7. Update the parent PRD

Read `{{PRD_PATH}}` again, then write it back with the `blocks:`
field updated to include wikilinks to all new children. Preserve
everything else exactly as-is.

### 8. Validate

Run `uv run prd validate` and fix any errors. Repeat until
validation passes cleanly.

### 9. Stage your changes

```bash
git add .darkfactory/prds/
git status
```

### 10. Report

Print a summary of the decomposition:

- How many child PRDs were created
- The dependency graph (which tasks depend on which)
- Any decisions or trade-offs you made

### 11. Emit the sentinel

Your final line must be exactly:

`PRD_EXECUTE_OK: {{PRD_ID}}`
