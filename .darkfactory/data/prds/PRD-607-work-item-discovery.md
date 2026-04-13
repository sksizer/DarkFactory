---
id: PRD-607
title: "Interactive Work Item Discovery"
kind: epic
status: draft
priority: medium
effort: l
capability: complex
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/cli/main.py
  - src/darkfactory/discover.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - onboarding
  - adoption
  - discovery
  - cli
  - feature
value: 5
---

# Interactive Work Item Discovery

## Summary

A CLI command (`prd discover`) that scans the codebase for existing work items — TODO/FIXME comments in code, outstanding PR review comments, and similar deferred-work markers — and walks the user through them interactively, allowing them to promote selected items into draft PRDs. The goal is to lower the adoption barrier for DarkFactory by capturing the work that already exists in a codebase rather than requiring users to start from scratch.

## Motivation

When a team adopts DarkFactory, they don't start with a blank slate. Their codebase already contains deferred work scattered across TODO comments, suppressed lint warnings, and unresolved PR feedback. Today, capturing this work into PRDs is entirely manual — someone has to grep for TODOs, read through PR threads, and hand-write each PRD. This is tedious enough that most of it never happens, which means the PRD system starts incomplete and stays that way.

An interactive discovery command solves this by:
1. **Automating the scan** — find work items across multiple sources in one pass
2. **Presenting items for triage** — the user reviews each item (or cluster) and decides: promote to draft PRD, skip, or ignore permanently
3. **Creating well-formed PRDs** — promoted items become properly structured draft PRDs with source references, ready for prioritization

## Discovery Sources

### Phase 1: Code Comments
Scan source files for inline markers indicating deferred work:
- `TODO`, `FIXME`, `HACK`, `XXX`, `WORKAROUND` — standard work-deferral markers
- `NOQA`, `type: ignore`, `@SuppressWarnings`, `nolint` — suppressed diagnostics (these represent acknowledged but unaddressed issues)
- Configurable additional patterns via `config.toml`

### Phase 2: PR Review Comments
Scan outstanding (unresolved) comments on open and recently merged PRs via `gh` CLI:
- Unresolved review threads on open PRs
- Comments on recently merged PRs that were never addressed (configurable lookback window)
- Filter to actionable comments (skip approvals, nits marked as such, etc.)

### Future Sources (out of scope for this PRD)
- GitHub Issues assigned to or mentioning the repo
- `CHANGELOG` entries marked as planned/upcoming
- Failing or skipped tests (`@pytest.mark.skip`, `@unittest.skip`)

## Requirements

### R1: Scanner Framework
1. A pluggable scanner architecture where each discovery source is a separate scanner class
2. Each scanner produces a common `DiscoveredItem` data structure containing: source location (file:line or URL), raw text, suggested title, suggested kind (task/feature), and scanner name
3. Scanners run independently and can be enabled/disabled via config

### R2: Code Comment Scanner
1. Walks all git-tracked files (respects `.gitignore` by default)
2. Matches configurable marker patterns (default: `TODO`, `FIXME`, `HACK`, `XXX`, `WORKAROUND`)
3. Extracts the marker and surrounding context (the comment text, and optionally 1-2 lines of adjacent code for context)
4. Supports configurable include/exclude glob patterns for file filtering
5. Handles multi-line comments (continuation lines following a TODO marker)

### R3: PR Comment Scanner
1. Uses `gh` CLI to fetch both unresolved and resolved review comments from open PRs
2. Fetches comments from recently merged PRs (configurable lookback: default 30 days)
3. Extracts comment body, file path, author, and PR reference
4. Uses an AI agent pass to classify comments as actionable deferred work vs. noise (approvals, nits, resolved discussions, style preferences). Only actionable items proceed to triage.

### R4: Clustering
1. **Same-file grouping** (primary): multiple markers in the same file are presented as a single cluster with option to split
2. **Cross-file exact match**: after stripping the marker prefix (`TODO:`, `FIXME:`, etc.) and normalizing whitespace, items with identical text across files are grouped together
3. **Tag-based grouping**: markers using a shared tag convention (e.g., `TODO(PROJ-123)`, `TODO(@alice)`) are grouped by tag
4. Clustering is best-effort; the user always has final say during interactive triage
5. Each cluster shows: count of items, file locations, representative text
6. Future: fuzzy/semantic similarity clustering is explicitly out of scope for v1

### R5: Interactive Triage CLI
1. Presents discovered items one at a time (or one cluster at a time)
2. For each item/cluster, the user can:
   - **Promote** (`y`) — create a draft PRD from this item
   - **Skip** (`s`) — leave it for now, will appear again on next run
   - **Edit** (`e`) — edit the suggested title/description before promoting
   - **Split** (`x`) — break a cluster into individual items and triage each
   - **Quit** (`q`) — stop triage, keeping progress so far
3. Shows a progress indicator (e.g., `[3/47]`)
4. On promote: generates a draft PRD with:
   - Auto-generated ID (next flat PRD number)
   - Title derived from the marker text (user can edit)
   - `kind: task` (default, user can override)
   - `status: draft`
   - `source_ref` field in frontmatter linking back to origin (file:line or PR URL)
   - Body containing the original marker text and source context
5. Summary at the end: N promoted, N skipped, N total scanned

### R6: Configuration
The `[discover]` section in `config.toml` supports:
```toml
[discover]
# Marker patterns to scan for (regex, case-insensitive)
markers = ["TODO", "FIXME", "HACK", "XXX", "WORKAROUND"]

# File include patterns (glob). Empty = all tracked files.
include = []

# File exclude patterns (glob). Applied after include.
exclude = ["*.min.js", "*.generated.*"]

# Whether to respect .gitignore (default: true)
respect_gitignore = true

# PR comment lookback in days (0 = disabled)
pr_lookback_days = 30
```

### R7: `source_ref` Frontmatter Field
1. Add an optional `source_ref` field to the PRD schema that accepts a single string or a list of strings
2. Format: `file:path/to/file.py:42` for code comments, `pr:owner/repo#123:comment_id` for PR comments
3. When multiple sources map to one PRD (e.g., a cluster), `source_ref` is a list
4. Field is optional on all PRDs — not exclusive to discovered items

### R8: Deduplication
1. Before presenting items, check existing PRDs for a matching `source_ref` field
2. Items that already have a corresponding PRD are silently skipped

## Technical Approach

### Architecture

```
prd discover [--source code|pr|all] [--dry-run]
      │
      ▼
  DiscoveryEngine
      │
      ├── CodeCommentScanner    → walks git-tracked files, extracts markers
      ├── PRCommentScanner      → calls gh api, extracts unresolved threads
      └── (future scanners)
      │
      ▼
  Clusterer                     → groups related items
      │
      ▼
  InteractiveTriage             → prompts user, creates PRDs
```

### New Modules
- `src/darkfactory/discover.py` — `DiscoveryEngine`, `DiscoveredItem` dataclass, `Clusterer`
- `src/darkfactory/scanners/code_comments.py` — code marker scanner
- `src/darkfactory/scanners/pr_comments.py` — PR review comment scanner
- `src/darkfactory/cli/discover.py` — `cmd_discover` CLI handler + interactive triage loop

### Key Design Decisions
- **Interactive-first**: No intermediate file format. Items are scanned, clustered, and presented in a single CLI session. This keeps the adoption path simple.
- **Git-aware by default**: Uses `git ls-files` for file enumeration, which naturally respects `.gitignore` and only scans tracked content.
- **Pluggable scanners**: New sources can be added by implementing a simple `Scanner` protocol (`scan(config) -> list[DiscoveredItem]`), but we don't over-engineer the plugin system — it's just a protocol + a list in the engine.
- **Draft status only**: Discovered items always become `status: draft` PRDs. They enter the normal PRD lifecycle from there. No automatic prioritization or assignment.

## Acceptance Criteria

- [ ] `prd discover` scans code comments and presents them interactively
- [ ] User can promote, skip, edit, split, or quit during triage
- [ ] Promoted items create valid draft PRDs with correct frontmatter and `source_ref`
- [ ] Multiple TODOs in the same file are clustered into a single triage item
- [ ] Very similar TODOs across files are suggested as a single cluster
- [ ] `source_ref` deduplication prevents re-promoting already-captured items
- [ ] `[discover]` config section is read from `config.toml` with sensible defaults
- [ ] Include/exclude glob patterns filter scanned files correctly
- [ ] `respect_gitignore = true` (default) limits scan to git-tracked files
- [ ] `--source code` limits scan to code comments only
- [ ] `--source pr` limits scan to PR comments only
- [ ] `--dry-run` lists discovered items without entering interactive mode
- [ ] PR comment scanner fetches unresolved threads from open PRs
- [ ] PR comment scanner respects `pr_lookback_days` for merged PRs
- [ ] End-of-session summary shows counts of promoted/skipped/total items
- [ ] All new code has tests
- [ ] `prd discover --help` shows usage with examples

## Resolved Decisions

1. **`source_ref` scope**: Optional field on all PRDs, accepts single string or list. Not exclusive to discovered items.
2. **Clustering strategy**: Same-file grouping + cross-file exact text match (after stripping marker prefix, normalizing whitespace) + tag-based grouping. Fuzzy/semantic matching deferred to future work.
3. **Command placement**: Top-level `prd discover` subcommand.

## Resolved Decisions (continued)

4. **Suppressed diagnostics**: Not in the default marker set — too noisy. Documented as opt-in additions users can add to `markers` in `config.toml` (e.g., `"noqa"`, `"type: ignore"`).
5. **PR comment filtering**: Fetch both unresolved and resolved comments, then run an AI classification pass to surface only comments that represent genuine deferred work.

## Open Questions

(None remaining.)

## Assessment (2026-04-11)

- **Value**: 3/5 — the "onboarding a new project" story is real and
  useful, but today DarkFactory has exactly one project using it
  (itself). The marginal value on this repo is low because the
  codebase's TODOs are already mostly captured as PRDs. Rises to 4/5
  for a second-adopter scenario.
- **Effort**: l — two scanners (code comments, PR comments), clustering,
  interactive triage loop, config schema, `source_ref` field, AI
  classification pass for PR comments. This is multiple modules plus
  a real CLI subsurface.
- **Current state**: greenfield. No `discover.py`, no `scanners/`,
  no `cmd_discover`, no `source_ref` field on the PRD dataclass.
- **Gaps to fully implement**: every requirement (R1–R8) is new work.
- **Recommendation**: defer — good PRD quality, but not a good bet for
  the single-user era. When a second adopter seriously engages, this
  PRD rises to a do-next in the onboarding batch alongside PRD-608
  and PRD-564. Until then, the author's self-assigned `value: 5`
  frontmatter overstates the current-moment usefulness — the real
  current value is 3 and the PRD is primarily a capture of "what we'd
  need to smooth onboarding later."
