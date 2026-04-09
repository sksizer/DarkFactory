# Agent verification model

## Preference

**Prefer post-agent verification from the harness over tightening in-agent permissions.**

When a DarkFactory workflow agent produces bad output — wrong filenames, invalid PRD IDs, missing frontmatter fields, malformed wikilinks, etc. — the preferred fix is *harness-side* verification and recovery, not changing the agent's in-session tool permissions.

## Rationale

Playing whack-a-mole with agent tool allowlists and Claude Code's sandbox is a losing game:

- Every new failure mode pushes toward one of two bad places — "agent can do anything" (unsafe) or "agent can barely do its job" (useless).
- Permission grants are global per workflow: giving the planning agent `Bash(rm …)` to fix one failure mode grants it the ability to rm files in every other workflow run too.
- The Claude Code session sandbox is a second layer outside the harness's control; even if the workflow allowlist grants something, the sandbox can still refuse.
- An agent that discovers its permissions live (by trying 20 commands and getting blocked each time) burns its entire task budget on self-discovery rather than useful work.

Instead:

- **Trust the agent to do the forward/generative work.** It writes new files, edits existing ones, produces content.
- **Run verification and recovery from trusted Python code in the harness.** The harness process is not subject to agent sandbox restrictions; it can freely delete, rename, or reject files.
- **If the agent produced something invalid, the harness fixes it** — either by cleaning up automatically (e.g. deleting files with invalid IDs) or by re-invoking the agent with a clearer error message.

## How to apply this

When designing or modifying a workflow that has an agent task:

1. **For forward operations** (Read, Edit, Write, Glob, Grep, scoped Bash for the task's happy path), grant the agent what it needs.
2. **For destructive or recovery operations** (rm, mv, git rm, git clean, file rename, permission changes), do **not** grant them to the agent. Handle them from the harness via a post-agent builtin or shell task.
3. **For verification** (run `prd validate`, check outputs, count produced files), prefer a shell task in the workflow running outside the agent. The shell task can fail loudly and trigger `retry_agent` with structured feedback.
4. **When the agent makes a common mistake**, the fix is almost always a prompt clarification + harness verification, not a permission grant.

## Boundary

The agent's role is **creative/generative**. The harness's role is **safety/correctness**. When those roles blur, push toward the harness side.

## History

This preference was captured after a concrete failure (2026-04-08) running the planning workflow against PRD-549:

- PRD-549's decomposition body specified 9 children with alphabetic-suffix IDs (`PRD-549.3a` through `PRD-549.3i`).
- The planning agent faithfully created those files.
- `prd validate` correctly rejected every file — the PRD ID regex is numeric-only (`^PRD-\d+(?:\.\d+)*$`).
- The agent correctly diagnosed the issue and tried to rename/delete the 9 bad files.
- **Every** delete/rename attempt was blocked: `rm`, `mv`, `git rm`, `git clean`, `python os.unlink`, `Path.rename` — by the workflow allowlist and/or the Claude Code sandbox.
- The agent burned its 600-second task budget cycling through variations and timed out.

The instinctive fix was "add delete permissions to the planning workflow." We're deliberately not doing that. The better fix is a harness-side post-agent verification phase that cleans up invalid output in trusted Python — captured as a future PRD.

## Related PRDs

- `prds/PRD-554-planning-workflow-prompt-hardening.md` — prompt-level fixes to prevent this specific class of mistake (e.g. "numeric IDs only, no alphabetic suffixes").
- Future: a PRD for the harness-side post-agent verification phase described above.
