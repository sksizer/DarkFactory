---
id: "PRD-601"
title: "YAML date quoting consistency"
kind: task
status: blocked
priority: low
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - "src/darkfactory/cli/new.py"
  - "src/darkfactory/prd.py"
workflow: null
target_version: null
created: '2026-04-09'
updated: '2026-04-09'
tags:
  - harness
  - quality
---

# YAML date quoting consistency

## Problem

The codebase is inconsistent about quoting YAML date fields (`created`, `updated`) in PRD frontmatter. `set_status_at()` intentionally quotes `updated` to prevent PyYAML's timestamp resolver from coercing date strings to `datetime.date` objects on round-trip. However, `cmd_new` (and several manually-created PRDs) emit unquoted dates.

This was surfaced across multiple PR reviews:
- PR #128 (Copilot comment on `cli/new.py:106`)
- PR #143 (Copilot comments on PRD-559.1 through PRD-559.5 frontmatter)

## Requirements

1. `cmd_new` must emit quoted `created` and `updated` values (e.g., `created: '2026-04-09'`).
2. `dump_frontmatter` (or equivalent) should consistently quote date-like string fields.
3. Existing PRDs with unquoted dates should be migrated (can be a one-time script).
4. Add a test that round-trips a PRD through write/read and asserts date fields remain strings.

## Acceptance criteria

- [ ] `prd new` creates PRDs with quoted date fields
- [ ] Round-trip test passes (write PRD, read back, dates are `str` not `datetime.date`)
- [ ] No unquoted date fields in `.darkfactory/prds/` after migration

## Assessment (2026-04-11)

- **Value**: n/a — the condition is already met by a different route.
- **Effort**: xs (just flip status)
- **Current state**: drift / done. PRD-622's deterministic serializer
  in `src/darkfactory/model/_persistence.py` writes all date fields as
  quoted strings by construction. A grep across the 220 active PRD files
  shows every `created:` and `updated:` field is string-quoted. The
  round-trip test that would be required to close this PRD is implicitly
  covered by the deterministic-serialization contract in PRD-622.
- **Gaps to fully implement**:
  - None in code.
  - Optional: add an explicit round-trip test for date preservation (xs).
- **Recommendation**: supersede — flip status to `superseded` and
  point at PRD-622 as the delivery vehicle. The blocked status is what
  held this up; that block cleared when PRD-622 merged.
