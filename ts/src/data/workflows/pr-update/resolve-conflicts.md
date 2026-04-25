# Resolve merge conflicts

A `git merge` into this PR branch from its base has produced conflicts. Your job is to resolve every conflict and complete the merge so the branch can be pushed.

## Ground rules

- Preserve the intent of BOTH sides. Do not blindly delete one side. Read surrounding code to understand each hunk before choosing.
- Keep the PR's feature work intact. The purpose of this merge is to incorporate upstream changes, not to undo PR work.
- Match the PR's existing style and conventions.
- Never call `git merge --abort`. Never touch the remote. If you truly cannot resolve a conflict, stop and emit the failure sentinel.

## Procedure

1. Run `git status --porcelain` to list unmerged paths.
2. For each unmerged file:
   - Read the file to examine the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
   - Read the file's peer test (if any) and nearby callers to understand intent.
   - Edit the file to produce a correct, compilable result. Remove all conflict markers.
   - Stage the file with `git add <path>`.
3. When every unmerged file is staged, finalize the merge with `git commit --no-edit` (this uses git's default merge commit message).
4. Run `git status --porcelain` one more time. It must be empty.
5. Emit `PRD_EXECUTE_OK` to signal success.

If at any point you determine the conflicts cannot be safely resolved (for example, semantically incompatible changes), emit `PRD_EXECUTE_FAILED: <short reason>` and stop. Do not abort the merge — the workflow will do that.
