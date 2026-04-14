---
id: PRD-561
title: Establish a skill to help discuss and create detailed PRDs
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - python/darkfactory/cli/
  - python/darkfactory/data/commands/
  - python/darkfactory/workflows/prd-authoring/
  - .claude/commands/
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-09'
updated: '2026-04-11'
tags: [authoring, skill, workflow, feature]
---

# Establish a skill to help discuss and create detailed PRDs

## Summary

Create a two-part PRD authoring system: (1) an interactive Claude Code slash command (`/prd-create`) that guides users from a rough idea through structured discussion to a complete, high-quality PRD, and (2) a DarkFactory workflow (`prd-authoring`) that can refine and validate PRDs programmatically. Together they eliminate the blank-page problem and enforce the level of detail seen in the project's best PRDs (e.g. PRD-222, PRD-224, PRD-541).

## Motivation

Today, running `prd new "My Idea"` produces an empty template with placeholder comments. The author must then manually fill every section — Summary, Motivation, Requirements, Technical Approach, Acceptance Criteria, Open Questions — from scratch. This leads to two recurring problems:

1. **Blank-page paralysis.** Users stare at the empty template and either write too little (vague one-liners) or skip sections entirely, producing PRDs that aren't actionable by the harness.
2. **Quality inconsistency.** The best PRDs in this project (PRD-222, PRD-224, PRD-541) have numbered functional requirements, testable ACs, concrete technical approaches with code sketches, and explicit dependency graphs. But nothing in the tooling guides authors toward that bar — quality depends entirely on individual discipline.

Without this skill, every new PRD is a coin flip between "ready for execution" and "needs two more rounds of back-and-forth to be usable." The planning workflow downstream suffers when it receives under-specified input.

## Requirements

### Functional

1. **Slash command `/prd-create`** — an interactive Claude Code skill that:
   a. Accepts an optional initial idea/title as an argument (e.g. `/prd-create "Add webhook support"`).
   b. Asks structured, adaptive questions to elicit the information needed for each PRD section. Questions should be driven by what's missing, not a fixed script — if the user provides a detailed initial description, skip the basics.
   c. Probes for scope boundaries: what is explicitly out of scope, what the user expects the `kind` to be (epic/feature/task), and whether decomposition is needed.
   d. Suggests `depends_on` and `blocks` relationships by querying existing PRDs in `.darkfactory/data/prds/` for related work.
   e. Drafts each section incrementally, showing the user what it will write and incorporating feedback before moving on.
   f. Generates numbered functional and non-functional requirements (not vague bullets).
   g. Generates testable acceptance criteria in `AC-N` format, each tied to a specific requirement.
   h. Proposes a technical approach section with affected modules and, for task-level PRDs, code sketches.
   i. Tags open questions as OPEN, and asks the user whether any can be resolved during the discussion.
   j. Calls `prd new` (or writes the file directly) to create the final `.md` file with fully populated frontmatter and body.
   k. After creation, offers to run a quality review (see requirement 3).

2. **Slash command `/prd-refine`** — a review/refinement skill that:
   a. Takes an existing PRD identifier (e.g. `/prd-refine PRD-561`) and reads the current file.
   b. Evaluates completeness against a quality rubric (see requirement 4).
   c. Reports gaps, weak spots, and suggestions as a structured checklist.
   d. Offers to fix issues interactively — the user can accept, reject, or modify each suggestion.
   e. Can transition status from `draft` to `ready` when all rubric criteria pass and the user confirms.

3. **DarkFactory workflow `prd-authoring`** — an automated workflow that:
   a. Applies to PRDs with `workflow: prd-authoring` (or is invokable via `prd run PRD-X --workflow prd-authoring`).
   b. Reads the current PRD content and evaluates it against the quality rubric.
   c. Uses an AgentTask to propose improvements, fill gaps, and strengthen weak sections.
   d. Emits a structured review report (pass/fail per rubric item) before applying changes.
   e. Does not auto-merge changes — produces a diff or branch for human review.

4. **Quality rubric** — a shared checklist used by both `/prd-refine` and the workflow:
   a. Summary is 1–3 sentences and states both what and why.
   b. Motivation explains the problem, who benefits, and cost of inaction.
   c. Functional requirements are numbered, specific, and testable.
   d. Non-functional requirements are present (at least one).
   e. Technical approach names affected modules/files; for tasks, includes code-level detail.
   f. Every AC maps to at least one requirement and is independently verifiable.
   g. Frontmatter fields `kind`, `priority`, `effort`, and `capability` are set (not null).
   h. `depends_on` / `blocks` are populated or explicitly empty with justification.
   i. Open questions are tagged OPEN/RESOLVED/DEFERRED.
   j. For epics/features: a decomposition section exists with child PRD sketches.

5. **Context awareness** — the skill should:
   a. Read existing PRDs to understand naming conventions, ID numbering, and tag patterns.
   b. Reference the project's source tree to ground technical approach suggestions in actual module paths.
   c. Warn if a proposed PRD overlaps significantly with an existing one.

6. **Lifecycle support** — beyond creation:
   a. `/prd-create` can resume an interrupted session if the user provides a draft PRD ID.
   b. `/prd-refine` can be run multiple times, tracking which rubric items were previously flagged.
   c. Status transitions: the skill can move a PRD from `draft` → `ready` (after rubric passes) or suggest `blocked` if unresolved dependencies are detected.

7. **Project initialization (`prd init`)** — slash commands are installed as part of project setup:
   a. `prd init` bootstraps the `.claude/` directory structure in the project root, including `.claude/commands/prd-create.md` and `.claude/commands/prd-refine.md`. (`prd init` already exists and scaffolds `.darkfactory/data/prds/` and `.darkfactory/data/archive/`; this PRD adds the `.claude/commands/` bootstrap on top.)
   b. If `.claude/commands/` already exists, only missing command files are added — existing files are never overwritten.
   c. Slash command files are bundled with the `darkfactory` package as package data (e.g. `python/darkfactory/data/commands/`) and copied into the project on init.
   d. `prd init` is idempotent — running it multiple times on the same project is safe and only adds what's missing.
   e. Prints a summary of what was created/skipped so the user knows what changed.

### Non-Functional

1. **Conversational, not interrogative.** The slash command should feel like a design discussion with a knowledgeable colleague, not a form to fill out. It should offer opinions, push back on vague requirements, and suggest alternatives.
2. **Respect existing patterns.** Generated PRDs must match the formatting, frontmatter schema, and section ordering used by existing PRDs in the project — not invent new conventions.
3. **Idempotent refinement.** Running `/prd-refine` on an already-complete PRD should report "all criteria pass" and not introduce unnecessary changes.
4. **No hallucinated dependencies.** When suggesting `depends_on` or `blocks`, only reference PRD IDs that actually exist in `.darkfactory/data/prds/`.

## Technical Approach

### Slash command (`/prd-create`, `/prd-refine`)

- Implemented as Claude Code custom slash commands in `.claude/commands/prd-create.md` and `.claude/commands/prd-refine.md`.
- Each command file contains the system prompt that guides Claude through the interactive workflow.
- `/prd-create` prompt structure:
  1. Role framing: "You are a product requirements analyst for the DarkFactory project..."
  2. Context injection: instruct Claude to read `.darkfactory/data/prds/` for existing PRDs, source tree for module paths.
  3. Conversation flow: elicit idea → clarify scope → draft sections iteratively → write file.
  4. Quality gate: run rubric check before finalizing.
- `/prd-refine` prompt structure:
  1. Read the target PRD file.
  2. Evaluate against the rubric (requirement 4).
  3. Present findings and offer interactive fixes.

### DarkFactory workflow (`prd-authoring`)

- New directory: `python/darkfactory/workflows/prd-authoring/`
  - `workflow.py` — exports a `Workflow` with `applies_to` matching `workflow: prd-authoring`.
  - `prompts/role.md` — frames the agent as a PRD quality reviewer.
  - `prompts/task.md` — injects the target PRD content and rubric, instructs agent to propose improvements.
  - `prompts/verify.md` — re-checks rubric after agent changes.
- Task sequence:
  1. `BuiltIn("ensure_worktree")` — isolate changes.
  2. `AgentTask("review-and-refine")` — evaluate + propose changes, constrained tool set (Read, Edit on `.darkfactory/data/prds/`).
  3. `BuiltIn("commit")` — commit improvements.
  4. `BuiltIn("push_branch")` — push for review.
  5. `BuiltIn("create_pr")` — open PR with rubric report in description.

### Project initialization (`prd init`)

- Extend the existing `prd init` subcommand in `python/darkfactory/cli/init_cmd.py` (backed by `python/darkfactory/init.py`). The command already creates `.darkfactory/data/prds/` and `.darkfactory/data/archive/`; this PRD adds the `.claude/commands/` bootstrap.
- Slash command source files are stored as package data in `python/darkfactory/data/commands/prd-create.md` and `python/darkfactory/data/commands/prd-refine.md`.
- Included in the package via `pyproject.toml` package-data configuration.
- `prd init` additions:
  1. Create `.claude/commands/` if missing.
  2. For each bundled command file, copy to `.claude/commands/` only if the target doesn't already exist.
  3. Print a summary: `Created .claude/commands/prd-create.md`, `Skipped .claude/commands/prd-refine.md (already exists)`, etc.
- Future skills (beyond this PRD) follow the same pattern — add source to `data/commands/`, `prd init` picks them up automatically.

### Quality rubric

- Defined as a data structure (list of `RubricItem` with name, description, and check function) in the workflow's prompt, not as code — since both the slash command and workflow consume it as natural language instructions.
- Rubric is maintained in a single shared file (e.g. `prompts/rubric.md`) referenced by both the slash commands and the workflow prompts.

## Acceptance Criteria

- [ ] AC-1: `/prd-create` is available as a Claude Code slash command and produces a fully populated PRD file in `.darkfactory/data/prds/` with correct frontmatter and all body sections filled.
- [ ] AC-2: `/prd-create` asks adaptive questions — skipping sections the user has already provided detail for — rather than following a rigid script.
- [ ] AC-3: `/prd-create` suggests `depends_on`/`blocks` relationships based on existing PRDs and does not reference non-existent PRD IDs.
- [ ] AC-4: `/prd-refine PRD-X` reads the target PRD, evaluates it against the quality rubric, and reports a structured pass/fail checklist.
- [ ] AC-5: `/prd-refine` can interactively fix flagged issues with user approval and transition status to `ready` when all criteria pass.
- [ ] AC-6: The `prd-authoring` workflow exists at `python/darkfactory/workflows/prd-authoring/` and can be invoked via `prd run`.
- [ ] AC-7: The workflow produces a PR with proposed PRD improvements and a rubric report in the PR description.
- [ ] AC-8: Generated PRDs match the formatting, frontmatter schema, and section ordering of existing project PRDs (validated by `prd validate`).
- [ ] AC-9: Running `/prd-refine` on a PRD that already meets all rubric criteria reports "all criteria pass" and makes no changes.
- [ ] AC-10: The quality rubric is maintained in a single shared location and used by both slash commands and the workflow.
- [ ] AC-11: `/prd-create` can resume from a draft PRD, picking up where the user left off.
- [ ] AC-12: `prd init` creates `.claude/commands/prd-create.md` and `.claude/commands/prd-refine.md` in the project root from bundled package data.
- [ ] AC-13: `prd init` is idempotent — running it twice does not overwrite existing command files or error out.
- [ ] AC-14: Slash command source files are included as package data and installed correctly via `pip install darkfactory`.

## Open Questions

- OPEN: Should `/prd-create` auto-assign the next available PRD ID, or prompt the user to choose one? Currently `prd new` handles ID assignment — the skill could delegate to it.
- OPEN: Should the rubric be configurable per-project (e.g. in `.darkfactory/config.toml`), or is a single hardcoded rubric sufficient for v1?
- OPEN: How should the slash command handle epics that need decomposition — should it also create the child PRD stubs, or just sketch them in the decomposition section and leave creation to a follow-up `/prd-create` per child?
- DEFERRED: Integration with issue trackers (GitHub Issues, Linear) for bi-directional sync of PRD status.
- DEFERRED: PRD templates per `kind` (epic template vs. task template) with different default sections and rubric weights.

## References

- PRD-222 (general-purpose tool epic) — example of a well-structured epic with decomposition
- PRD-224 (harness invariants) — example of detailed motivation with incident-driven requirements
- PRD-541 (color output) — example of a complete feature-level PRD
- PRD-510 (prd new subcommand) — the existing `prd new` implementation this skill builds on
- `python/darkfactory/workflows/planning/` — existing planning workflow, pattern reference for the new workflow
- `python/darkfactory/workflows/default/` — default workflow, structural reference

## Assessment (2026-04-11)

- **Value**: 3/5 — the "blank page paralysis" problem is real, but
  the project's existing PRD-616 (`prd discuss`) command already
  covers most of the same territory for interactive discussion. This
  PRD's additional value is (a) the `/prd-refine` rubric check and
  (b) the `prd-authoring` workflow for programmatic refinement.
- **Effort**: m — the slash-command side is small (markdown files).
  The `prd-authoring` workflow + `prd init`-side bundling + package
  data wiring is where the real work is. The rubric content is easy
  to write; enforcing it via AC-8 (matching formatting / section
  ordering) requires tests against existing PRD files.
- **Current state**: partially scaffolded for the adjacent work
  (PRD-616's `cli/discuss.py` already exists). No `/prd-create` or
  `/prd-refine` skill files. No `prd-authoring` workflow.
- **Gaps to fully implement**:
  - Author `/prd-create` and `/prd-refine` skill files (markdown).
  - Bundle them as package data under
    `python/darkfactory/data/commands/`.
  - Extend `prd init` (or `init_cmd.py`) to copy them into
    `.claude/commands/`.
  - Create `workflows/prd-authoring/` with role/task/verify prompts.
  - Rubric as a shared markdown file both the skill and workflow
    consume.
  - Tests for idempotent re-init, generated-PRD shape.
- **Recommendation**: defer — `prd discuss` (PRD-616) already landed
  and is conceptually the same thing. Before building this PRD,
  evaluate whether extending `prd discuss` with a rubric pass covers
  enough of R2/R3 to make the standalone `/prd-refine` unnecessary.
  If yes, this PRD shrinks to "add a rubric + quality gate to the
  existing discuss flow," which is s-effort and could be a
  do-next. The current PRD as written overlaps its predecessor.
