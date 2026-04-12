---
id: "PRD-601"
title: "YAML date quoting consistency"
kind: task
status: superseded
priority: low
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - "src/darkfactory/cli/new.py"
  - "src/darkfactory/model/_persistence.py"
workflow: null
target_version: null
created: '2026-04-09'
updated: '2026-04-11'
tags:
  - harness
  - quality
---

# YAML date quoting consistency

## Superseded by

PRD-622 (Data Model Refactor, now merged) delivered a deterministic frontmatter serializer in `src/darkfactory/model/_persistence.py`. `_format_scalar` now explicitly single-quotes `date` objects and any string matching `\d{4}-\d{2}-\d{2}` (dates), and double-quotes wikilinks. Every `save()` path goes through this serializer, so all `created`/`updated` fields written by the harness are consistently quoted. `prd new` uses the same write path, and existing PRDs are re-serialized on their next write. This PRD's scope is fully delivered.

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
