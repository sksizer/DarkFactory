# Review Guide

Follow these heuristics when auditing a partially-decomposed epic.

## Coverage analysis

- Read every existing child PRD's **Summary** and **Requirements**
  sections carefully.
- Build a **coverage matrix**: for each requirement in the parent,
  which child(ren) implement it?
- A requirement is "covered" if at least one child's stated purpose
  addresses the requirement's intent — not necessarily verbatim.
- If a requirement is too abstract to verify coverage, flag it in
  your summary ("requirement N is too abstract to verify coverage")
  rather than fabricating a child for it.

## Identifying gaps

- A requirement with **no** implementing child is a gap.
- A requirement that is **partially** covered (e.g. one slice of a
  multi-part requirement is handled) may or may not need a new child.
  Use judgment — if the existing child can reasonably grow to cover
  the full requirement, it's not a gap.

## Creating new children

- Don't create overlapping children. If a requirement is partially
  covered by an existing child, prefer flagging the partial coverage
  in your summary over creating a duplicate.
- New children should follow the **same conventions** as existing
  siblings: ID format, frontmatter shape, body structure.
- Pick child IDs that don't collide with existing siblings: glob
  `.darkfactory/prds/PRD-{parent_number}.*.md` and use the next unused index.

## ID conventions

- Use **hierarchical IDs**: children of `PRD-X` get `PRD-X.1`,
  `PRD-X.2`, etc.
- The slug in the filename should be a short kebab-case summary:
  `PRD-222.5-add-retry-logic.md`.

## PRD file format

Each new task PRD must have:

- **Valid YAML frontmatter** with all required fields:
  - `id`: quoted string, e.g. `"PRD-222.5"`
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

- After creating new child PRDs, update the parent PRD's `blocks:`
  field to include wikilinks to **all** children (existing + new).
- Read the parent PRD first, then write it back with only the
  `blocks:` field changed. Preserve all other content byte-for-byte.

## When everything is covered

If the existing children already cover all of the parent's
requirements, that is a **valid result**. Do not create unnecessary
children just to have output. Instead:

- Print "Decomposition complete — all N requirements covered by
  existing children"
- Emit the sentinel with a `complete: no gaps found` line.

## Validation

- Run `uv run prd validate` after creating all files.
- Fix any validation errors before declaring done.
- Common errors: missing required fields, malformed wikilinks,
  duplicate IDs, broken parent references.
