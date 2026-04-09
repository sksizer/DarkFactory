# Task: Decompose {{TARGET_PRD}} into child task PRDs

You are working inside a git worktree on branch `{{BRANCH_NAME}}`.

Your goal is to read the target PRD and produce well-formed child task PRDs
that fully decompose the parent into implementable units.

## Steps

### 1. Read the target PRD

Read the target PRD file from the `.darkfactory/prds/` directory. The target
PRD ID is `{{TARGET_PRD}}`. Find the file by globbing
`.darkfactory/prds/{{TARGET_PRD}}-*.md`.

Pay particular attention to:

- **Requirements** — the functional constraints and deliverables.
- **Technical Approach** — file paths, function signatures, and
  implementation patterns. These are your primary decomposition seams.
- **Acceptance Criteria** — these inform what each child task must deliver.

If the PRD references other PRDs or design docs, read those too for context.

### 2. Study the PRD format

Glob `.darkfactory/prds/PRD-*.md` to find existing well-formed `kind: task`
PRDs and use one as a format reference. Note all required frontmatter fields.

### 3. Survey existing PRDs

Note the ID numbering scheme so your new children don't collide with existing
IDs.

### 4. Identify decomposition seams

Based on the target PRD's structure, identify the natural task boundaries.
Consider:

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
- Set `kind: task`, `status: ready`
- Set `parent` to the target PRD wikilink
- Write substantive body sections (Summary, Requirements, Technical
  Approach with file paths, Acceptance Criteria)

### 7. Update the parent PRD

Read the target PRD again, then write it back with the `blocks:` field
updated to include wikilinks to all new children. Preserve everything
else exactly as-is.

### 8. Validate

Run `uv run prd validate` and fix any errors. Repeat until validation
passes cleanly.

### 9. Report

Print a summary of the decomposition:

- How many child PRDs were created
- The dependency graph (which tasks depend on which)
- Any decisions or trade-offs you made

### 10. Emit the sentinel

Your final line must be exactly:

`PRD_EXECUTE_OK: {{TARGET_PRD}}`
