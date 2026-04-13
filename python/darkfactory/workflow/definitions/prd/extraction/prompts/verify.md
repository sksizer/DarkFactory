# Verification retry

A previous step failed. The failing command output was:

```
{{CHECK_OUTPUT}}
```

Investigate the failure in the target repo, fix the underlying issue,
and re-run the verification commands the PRD's Acceptance Criteria
require. Then emit the sentinel as before.
