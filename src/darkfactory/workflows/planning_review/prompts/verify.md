# Verification Retry

The `prd validate` check failed after your planning review. The harness
is giving you one retry to fix the issue.

## Failed check output

```
{{CHECK_OUTPUT}}
```

## Your task

1. Read the failure output above carefully. Identify which PRD files
   have validation errors and what specifically is wrong.
2. Fix each broken PRD file — common issues include:
   - Missing required frontmatter fields
   - Malformed wikilinks (must be `"[[PRD-ID-slug]]"` format)
   - Duplicate PRD IDs
   - Invalid `parent` references
   - Invalid field values (bad kind, status, effort, etc.)
3. If the parent PRD's `blocks:` field is malformed, fix that too.
4. Re-run `uv run prd validate` to verify the fix.
5. Stage your changes:
   ```bash
   git add .darkfactory/prds/
   git status
   ```
6. Emit the sentinel line:
   - `PRD_EXECUTE_OK: {{PRD_ID}}` on success
   - `PRD_EXECUTE_FAILED: <reason>` if you cannot fix the issue

You have **one** retry — if validation fails again after this, the
harness will mark the PRD blocked.
