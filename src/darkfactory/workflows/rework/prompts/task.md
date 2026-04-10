# Rework: address PR review feedback for {{PRD_ID}}

## Original PRD
Read the PRD at `{{PRD_PATH}}` for context on what was implemented.

## Your previous work
The git history on this branch shows what you committed. Use
`git log` and `git diff {{BASE_REF}}...HEAD` to see what's already done.

## Review feedback to address

{{REWORK_FEEDBACK}}

## Steps

1. Read each comment carefully. Note the `thread_id` shown in each heading.
2. For each comment, decide: address it (edit code) OR push back
   (note why you disagree).
3. Make the necessary code edits.
4. For each comment, prepare a one-line reply note:
   - "Addressed: <what you changed>"
   - "Disagree: <reason>"
   - "Already addressed in prior commit (please re-review)"
5. Stage all your changes — the harness commits and pushes.
6. After staging, emit your reply notes as a fenced JSON block so the
   harness can post them back to GitHub. Use the exact `thread_id` from
   each comment heading:

```json-reply-notes
[
  {"thread_id": "<thread_id_from_comment_heading>", "note": "Addressed: <what you changed>"},
  {"thread_id": "<another_thread_id>", "note": "Disagree: <reason>"}
]
```

   Include one entry per comment thread you addressed or responded to.
   Omit threads you intentionally skipped.
