# Decomposition Guide

Follow these heuristics when breaking an epic or feature into tasks.

## Granularity

- Each task should represent **1-4 hours** of solo-implementable work.
- A task is something one engineer can pick up and complete in a single
  focused session without needing to coordinate with others mid-task.
- If a task feels like it needs sub-tasks, it's too big — split it.

## Ordering and dependencies

- **API and contract definition** before backend before frontend.
- **Pure functions** before commands before UI.
- Earlier sibling tasks should unblock later ones.
- Set `depends_on` between siblings where execution order matters.
- Tasks that can run in parallel should have no dependency between them.

## Decomposition seams

- Decompose along **natural interface boundaries** (modules, APIs,
  data models, UI components).
- Use the parent PRD's existing structure (Requirements, Technical
  Approach) as ground truth for what the work entails.
- Look for explicit file paths and function signatures in the parent
  PRD — these often correspond to individual tasks.

## ID conventions

- Use **hierarchical IDs**: children of `PRD-X` get `PRD-X.1`,
  `PRD-X.2`, etc.
- Pick the next unused sibling index by globbing
  `.darkfactory/prds/PRD-{parent_number}.*.md` to see what already exists.
- The slug in the filename should be a short kebab-case summary:
  `PRD-222.1-define-tool-schema.md`.

## PRD file format

Each new task PRD must have:

- **Valid YAML frontmatter** with all required fields:
  - `id`: quoted string, e.g. `"PRD-222.1"`
  - `title`: quoted string
  - `kind: task`
  - `status: ready`
  - `priority`: inherit from parent or use `medium`
  - `effort`: estimate (`xs`, `s`, `m`, `l`, `xl`)
  - `capability`: estimate (`trivial`, `simple`, `moderate`, `complex`)
  - `parent`: wikilink to the parent PRD, e.g. `"[[PRD-222-general-purpose-tool]]"`
  - `depends_on`: list of wikilinks to sibling tasks this depends on
  - `blocks`: list of wikilinks to tasks this blocks (usually `[]`)
  - `impacts`: list of file paths this task will modify
  - `workflow: null` (let the assignment logic pick the right workflow)
  - `target_version: null`
  - `created`: today's date (YYYY-MM-DD)
  - `updated`: today's date (YYYY-MM-DD)
  - `tags`: relevant tags from the parent
- **Body sections**: Summary, Requirements, Technical Approach (with
  file paths and function signatures where possible), Acceptance
  Criteria.

## Updating the parent PRD

- After creating all child PRDs, update the parent PRD's `blocks:`
  field to include wikilinks to every new child.
- Read the parent PRD first, then write it back with only the
  `blocks:` field changed. Preserve all other content byte-for-byte.

## Validation

- Run `uv run prd validate` after creating all files.
- Fix any validation errors before declaring done.
- Common errors: missing required fields, malformed wikilinks,
  duplicate IDs, broken parent references.
