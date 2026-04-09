# Rework: address PR review feedback for {{PRD_ID}}

## Original PRD
Read the PRD at `{{PRD_PATH}}` for context on what was implemented.

## Your previous work
The git history on this branch shows what you committed. Use
`git log` and `git diff {{BASE_REF}}...HEAD` to see what's already done.

## Review feedback to address

{{REWORK_FEEDBACK}}

## Steps

1. Read each comment carefully.
2. For each comment, decide: address it (edit code) OR push back
   (note why you disagree).
3. Make the necessary code edits.
4. For each comment, prepare a one-line reply note:
   - "Addressed: <what you changed>"
   - "Disagree: <reason>"
   - "Already addressed in prior commit (please re-review)"
5. Stage all your changes — the harness commits and pushes.
