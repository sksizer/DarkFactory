---
id: PRD-562
title: Build a skill to review DarkFactory PRDs and look for the highest impact draft
  to work on readying for implementation
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - .claude/skills/prd-triage/SKILL.md
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-09'
updated: '2026-04-11'
tags:
  - skills
  - process
  - triage
  - feature
---

# Build a skill to triage draft PRDs and ready the highest-impact one

## Summary

Create a Claude Code skill (`/prd-triage`) that scans all `draft` PRDs, scores them on impact and readiness-to-ready, and either presents a ranked shortlist or immediately begins fleshing out the top pick — filling in requirements, acceptance criteria, technical approach, and decomposition so the PRD can transition from `draft` to `ready`.

The gap between `draft` and `ready` is the biggest bottleneck in the harness pipeline: `prd run` can only execute PRDs in `ready` status, and many drafts sit indefinitely because nobody has done the design work to promote them. This skill automates the triage + promotion loop.

## Motivation

### The problem

DarkFactory currently has ~15–20 draft PRDs at any given time. Each is a captured idea — sometimes a one-liner, sometimes a detailed design sketch — but none can be executed by the harness until someone:

1. Fills in concrete requirements (numbered, testable)
2. Writes acceptance criteria (AC-1, AC-2, …)
3. Specifies a technical approach (affected modules, data flow)
4. Decomposes epics/features into task-level children
5. Sets accurate `effort`, `capability`, and `priority` metadata
6. Resolves or defers open questions

This is skilled design work that requires understanding the codebase, the PRD DAG, and the project's current priorities. Today it's done manually, one PRD at a time, with no systematic way to decide which draft to tackle first.

### Why a skill

- **Repeatable**: the triage logic runs the same way every time — no reinventing the analysis each session.
- **Context-aware**: the skill can read the full PRD DAG, check `prd validate` output, scan the codebase, and use web search — all within a single invocation.
- **Incremental**: the user can run `/prd-triage` whenever they have a spare session and chip away at the backlog.
- **Opinionated by default, overridable**: the scoring heuristic encodes project priorities, but the user can override with `/prd-triage PRD-543` to target a specific draft.

## Requirements

### Functional

1. The skill is invocable as `/prd-triage` (no arguments = auto-select) or `/prd-triage PRD-XXX` (target a specific draft).
2. **Scan phase**: read all PRDs from `.darkfactory/data/prds/`, filter to `status: draft`.
3. **Score phase**: rank each draft on a composite of:
   - **Priority** (`critical` > `high` > `medium` > `low`) — from frontmatter.
   - **Unblock potential** — how many other PRDs does this draft `block`? How many transitive dependents?
   - **Readiness gap** — how much work is needed to promote it? A draft with a detailed design sketch is cheaper to ready than a one-liner stub.
   - **Staleness** — older drafts with high priority may indicate forgotten important work.
   - **DAG position** — drafts that are leaves (no children, no blockers) are cheaper to ready than epics that need decomposition.
4. **Present phase**: display the top 5 ranked drafts with a one-line rationale for each score, and ask the user which to work on (or auto-select the top pick if `--auto` or no user interaction).
5. **Ready phase**: for the selected draft, perform the design work:
   a. Research the codebase — read affected files, understand existing patterns, check related PRDs.
   b. Fill in or refine the Summary, Motivation, Requirements, Technical Approach, and Acceptance Criteria sections.
   c. For epics/features: propose a decomposition into child task PRDs (but do not create the child files — just outline them in the PRD body).
   d. Validate metadata: ensure `effort`, `capability`, `priority`, `depends_on`, `blocks`, `impacts`, and `tags` are accurate given the design work.
   e. Resolve or tag each Open Question as `RESOLVED` or `DEFERRED` with rationale.
6. **Transition**: once the PRD is fully specified, flip `status: draft` → `status: ready` and update the `updated:` date.
7. The skill must not create new files (no child PRD files, no scratch files). It only modifies the target PRD's markdown file.

### Non-Functional

1. The skill should complete in under 5 minutes for a typical draft.
2. All changes are local (no git commits, no PRs) — the user reviews the diff and commits manually.
3. The skill should use `prd validate` or equivalent checks to ensure the readied PRD doesn't introduce DAG issues (cycles, orphaned deps).

## Technical Approach

The skill is a single markdown file at `.claude/skills/prd-triage/SKILL.md` following the existing skill authoring pattern.

**Workflow steps** (encoded as numbered instructions in the SKILL.md body):

1. Run `uv run prd status --json` (or read PRD files directly via Glob + Read) to collect all PRDs and their metadata.
2. Filter to `status: draft`. If `$0` is provided, select that specific PRD; otherwise proceed to scoring.
3. Score each draft using the heuristic described in Functional Requirement 3. Present the top 5 to the user with rationale.
4. For the selected PRD, read the file and identify which sections are incomplete (stub text, placeholder comments, empty lists).
5. Research: read files listed in `impacts`, grep for related symbols, read parent/sibling/blocking PRDs for context.
6. Write the missing sections directly into the PRD file using Edit tool calls.
7. Run `uv run prd validate` to check the result.
8. If validation passes, flip `status: draft` → `status: ready` and update `updated:` to today's date.
9. Report what changed and suggest the user review the diff with `git diff`.

**Allowed tools**: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch.

## Acceptance Criteria

- [ ] AC-1: `/prd-triage` with no arguments lists the top 5 draft PRDs ranked by impact score with a one-line rationale per entry.
- [ ] AC-2: `/prd-triage PRD-XXX` skips scoring and directly begins readying the named draft.
- [ ] AC-3: After the skill completes, the target PRD has non-placeholder content in Summary, Motivation, Requirements, Technical Approach, and Acceptance Criteria sections.
- [ ] AC-4: The target PRD's `status` is flipped from `draft` to `ready` and `updated` is set to today's date.
- [ ] AC-5: Running `prd validate` after the skill completes produces no new errors related to the readied PRD.
- [ ] AC-6: The skill does not create any new files — only the target PRD is modified.
- [ ] AC-7: The skill file exists at `.claude/skills/prd-triage/SKILL.md` with correct frontmatter (`name`, `description`, `allowed-tools`).

## Open Questions

- [DEFERRED] Should the skill also create child PRD files for epic/feature decomposition, or just outline them in the body? **Decision**: outline only for now — creating children is the planning workflow's job once the PRD is `ready`.
- [DEFERRED] Should the scoring heuristic be configurable (e.g., weights in `.darkfactory/config.toml`)? Premature — hardcode sensible defaults first, extract config if needed later.
- [OPEN] Should the skill commit and/or create a branch? Current leaning: no — keep it local so the user can review the diff before committing. The existing `/prd-work` skill handles the commit-and-PR flow.

## References

- Existing skills: `~/.claude/skills/prd-work/SKILL.md`, `~/.claude/skills/prd-driven-tasks/SKILL.md`
- PRD statuses and lifecycle: defined in the `src/darkfactory/model/` package (`model/_prd.py`, `model/_persistence.py`) frontmatter schema
- CLI commands useful for triage: `prd status`, `prd next`, `prd validate`, `prd tree`, `prd undecomposed`
- Example well-formed draft: `.darkfactory/data/prds/PRD-226-status-derived-from-events.md`
- Example stub draft needing work: `.darkfactory/data/prds/PRD-300-.md`

## Assessment (2026-04-11)

- **Value**: 3/5 — exactly the job this 2026-04-11 value/effort pass
  just did manually. The automated version would save a couple of
  hours per quarter if used that often. It would NOT (per the PRD's
  own AC-6) actually do implementation, so the "highest bottleneck"
  framing overstates the value slightly.
- **Effort**: s — the entire PRD is a single SKILL.md markdown file
  (per PRD's technical approach). No Python code.
- **Current state**: greenfield. No `.claude/skills/prd-triage/SKILL.md`.
- **Gaps to fully implement**:
  - Write the skill file with the numbered workflow steps.
  - Bundle it as package data alongside PRD-561's slash commands
    (or keep it global in `~/.claude/skills/`).
- **Recommendation**: do-next — low effort, quick payoff every time it
  runs, orthogonal to all other work. Pair with PRD-561 since both
  want the same `prd init` → `.claude/` bundling infrastructure.
  The PRD-562 skill file itself should reference this very assessment
  as the baseline "here's what the triage output looks like."
