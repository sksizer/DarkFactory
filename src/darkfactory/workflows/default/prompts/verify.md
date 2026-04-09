# Verification Retry

An automated check failed after your initial implementation. The
harness is giving you one retry to fix the issue.

## Failed check output

```
{{CHECK_OUTPUT}}
```

## Your task

1. Read the failure output above carefully. Identify the root cause —
   don't just paper over the symptom.
2. Fix the problem in code. If the failure reveals that your original
   implementation was wrong, revise it. If the tests themselves are
   broken, fix them.
3. Re-run the failing check locally to verify it now passes.
4. Stage and commit the fix with a conventional-commits message
   referencing `{{PRD_ID}}`.
5. Emit the sentinel line as before:
   - `PRD_EXECUTE_OK: {{PRD_ID}}` on success
   - `PRD_EXECUTE_FAILED: <reason>` if you cannot fix the issue

You have **one** retry — if the check fails again after this, the
harness will mark the PRD blocked.
