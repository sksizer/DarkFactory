# Batch 4 — Impact Assessment

## PRD-567.2.1 — Add explicit --disallowed-tools for harness-owned git operations
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `invoke.py` and `invoke_test.py`. No references to stale PRD paths, old module names, or `--prd-dir`. Technical approach still valid.

## PRD-567.2.2 — Harden role/task prompts against denial retry loops
- **Impact:** none
- **Changes made:** none
- **Notes:** Touches workflow prompt markdown files only. No stale references.

## PRD-567.3 — File operation permissions and workflow specialization
- **Impact:** none
- **Changes made:** none
- **Notes:** Umbrella feature PRD. No module paths or old PRD paths referenced.

## PRD-567.3.1 — Add file deletion permissions to task workflow
- **Impact:** none
- **Changes made:** none
- **Notes:** Single-line tools list change to `task/workflow.py`. No stale references.

## PRD-567.3.2 — Create refactor/cleanup workflow with broad file-operation permissions
- **Impact:** none
- **Changes made:** none
- **Notes:** New workflow creation under `workflows/refactor/`. Uses `PRD_IMPLEMENTATION_TEMPLATE.compose()` which still exists. No stale references.

## PRD-567.4 — Filesystem containment hardening (feature umbrella)
- **Impact:** minor
- **Changes made:**
  - Updated stale example path `.darkfactory/prds/...` to `.darkfactory/data/prds/...` in the Summary.
  - Bumped `updated` to `'2026-04-11'`.
- **Notes:** The containment approach itself (relative + absolute path blocking in `invoke.py`) is still valid.

## PRD-567.4.1 — Block absolute-path escapes in invoke.py
- **Impact:** minor
- **Changes made:**
  - Updated two stale example paths from `.darkfactory/prds/file.md` to `.darkfactory/data/prds/file.md` in the Summary.
  - Bumped `updated` to `'2026-04-11'`.
- **Notes:** Approach (repo-root blocking via `--disallowed-tools`) still sound. Open questions remain valid.

## PRD-567.4.2 — Post-invocation containment verification in runner
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `runner.py` and integration tests. Uses `git status --porcelain` approach — no stale references.

## PRD-567.5 — Align planning workflow with WorkflowTemplate
- **Impact:** none
- **Changes made:** none
- **Notes:** `planning/workflow.py` and `templates_builtin.py` still the right targets. `PRD_IMPLEMENTATION_TEMPLATE` still exists. Technical approach unchanged by PRD-622.

## PRD-567.6 — Structured failure context in event logs
- **Impact:** none
- **Changes made:** none
- **Notes:** Targets `event_log.py` and `runner.py`. Orthogonal to the data model refactor.

## Summary

- **Total PRDs touched:** 2 (PRD-567.4, PRD-567.4.1)
- **Impact breakdown:** 8 none, 2 minor, 0 major, 0 superseded
- **Flagged issues:** None. The 567.x workflow reliability family is almost entirely orthogonal to PRD-622: it targets `invoke.py`, `runner.py`, workflow prompts, and workflow predicates, not PRD data model code. Only the containment examples in 567.4 and 567.4.1 referenced the old `.darkfactory/prds/` path, and those were cosmetic example updates.
