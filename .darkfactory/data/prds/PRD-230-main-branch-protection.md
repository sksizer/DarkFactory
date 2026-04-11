---
id: "PRD-230"
title: "Main branch protection: refuse direct pushes locally and on GitHub"
kind: task
status: done
priority: medium
effort: xs
capability: trivial
parent: null
depends_on: []
blocks: []
impacts:
  - .git/hooks/pre-push
  - .github/settings.yml
  - scripts/install-hooks.sh
  - README.md
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - hygiene
  - safety
---

# Main branch protection: refuse direct pushes locally and on GitHub

## Summary

Prevent direct pushes to `main`. Two layers of defense:

1. **Local pre-push hook** at `.git/hooks/pre-push` that refuses any push whose target is `refs/heads/main`. Fast feedback — fails before the network round-trip — and works for any contributor (human or agent) running locally.
2. **GitHub branch protection rules** on `main` that require all changes to land via pull request and reject direct pushes server-side. Belt-and-suspenders for the case where the local hook is missing or bypassed with `--no-verify`.

A small `scripts/install-hooks.sh` symlinks the pre-push hook into `.git/hooks/` since git won't track files in that directory. README documents the install step.

## Motivation

**Concrete incident (2026-04-08):** during a design refresh session, an AI assistant ended up checked out on `main` after merges synced and committed two PRD design files (`PRD-228`, `PRD-229`) directly to main, bypassing the usual PR review path. The content was harmless docs, but the process broke the project's "everything goes through a PR" norm.

That's exactly the failure mode this PRD prevents. The `main` branch should be a **destination only** — a target for merges, never a target for `git push`. Making that an enforced rule (not a convention) eliminates the failure mode whether the contributor is a human in a hurry, an AI assistant that lost track of its branch, or a misconfigured automation script.

## Requirements

1. A pre-push hook script at `.scripts/git-hooks/pre-push` (tracked) that:
   - Reads stdin (git's pre-push contract)
   - For each `<local_ref> <local_sha> <remote_ref> <remote_sha>` line, checks if `remote_ref == refs/heads/main`
   - If so, prints a clear error message and exits non-zero
   - Otherwise exits 0
2. An installer script `scripts/install-hooks.sh` that symlinks the tracked hooks into `.git/hooks/`. Idempotent — re-running is a no-op.
3. README documents: "First time setup: run `./scripts/install-hooks.sh` after cloning."
4. A GitHub branch protection rule on `main`:
   - Require pull request before merging
   - Require at least 0 approvals (solo project for now; bump later)
   - Require status checks to pass (the existing CI from PRD-530 once that lands; until then no required checks)
   - Disallow force pushes
   - Disallow deletions
5. The protection rules are documented either in a `.github/settings.yml` file (managed by the [Settings App](https://github.com/apps/settings)) OR in README as a manual setup step. Recommendation: README + manual for now since adding the Settings App is its own bit of overhead.
6. Test: try to push directly to main from a clean checkout with hooks installed; expect failure with a clear message.

## Technical Approach

### `.scripts/git-hooks/pre-push`

```bash
#!/usr/bin/env bash
# Refuses any push targeting refs/heads/main on origin.
# Override with --no-verify if you really mean it (but you shouldn't).

set -euo pipefail

protected_branch="refs/heads/main"

while read -r local_ref local_sha remote_ref remote_sha; do
    if [ "$remote_ref" = "$protected_branch" ]; then
        echo ""
        echo "ERROR: direct push to main is not allowed."
        echo ""
        echo "  Local:  $local_ref ($local_sha)"
        echo "  Remote: $remote_ref"
        echo ""
        echo "Open a pull request instead:"
        echo "  1. Create a branch:  git checkout -b <type>/<short-description>"
        echo "  2. Push the branch:  git push -u origin <branch>"
        echo "  3. Open a PR:        gh pr create --base main"
        echo ""
        echo "If you absolutely must push to main, bypass with --no-verify."
        echo "(But you should not. The point of this hook is to make you stop and think.)"
        echo ""
        exit 1
    fi
done

exit 0
```

### `scripts/install-hooks.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/.scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
    echo "ERROR: $HOOKS_SRC not found"
    exit 1
fi

mkdir -p "$HOOKS_DST"

for hook in "$HOOKS_SRC"/*; do
    name="$(basename "$hook")"
    target="$HOOKS_DST/$name"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$hook" ]; then
        echo "  $name already linked"
        continue
    fi
    if [ -e "$target" ]; then
        echo "  $name exists (not a symlink) — backing up to $name.bak"
        mv "$target" "$target.bak"
    fi
    ln -s "$hook" "$target"
    chmod +x "$hook"
    echo "  $name installed"
done

echo ""
echo "Hooks installed. Re-run any time after cloning."
```

### GitHub branch protection (manual setup)

In repo Settings → Branches → Add rule for `main`:

- ✓ Require a pull request before merging
- ✓ Require linear history (optional, prevents merge commits if you prefer squash-only)
- ✓ Do not allow force pushes
- ✓ Do not allow deletions
- ✗ Approvals required: 0 (solo project, bump when collaborators join)

Document this in README under "Repo conventions" so anyone setting up a fork knows.

## Acceptance Criteria

- [ ] AC-1: `.scripts/git-hooks/pre-push` exists, is executable, and refuses pushes to `refs/heads/main` with a clear message
- [ ] AC-2: `scripts/install-hooks.sh` symlinks the hook into `.git/hooks/`; idempotent on re-run
- [ ] AC-3: After running the installer, `git push origin HEAD:main` from a feature branch fails with the hook's error message
- [ ] AC-4: The hook does NOT block pushes to feature branches (e.g. `git push -u origin feature/foo` works)
- [ ] AC-5: README documents the install step in the contributor setup section
- [ ] AC-6: GitHub branch protection rule is enabled on `main` (manually verified — no API automation in this PRD)
- [ ] AC-7: A test push directly to main from a fresh checkout (with hooks installed) fails locally before reaching the network

## Open Questions

- [ ] Should the hook also protect against pushes to `release/*` or other long-lived branches? Recommendation: not yet — only main exists today; revisit when there are multiple protected branches
- [ ] Should the installer be invoked automatically by `mise install` or `uv sync`? Tempting but invasive — recommendation: keep it explicit and documented. A user who's just inspecting the repo shouldn't have hooks silently installed
- [ ] Is `.scripts/git-hooks/` the right location vs `scripts/git-hooks/`? The dot-prefix is consistent with `.darkfactory/` (PRD-222) for "tooling state, not user code". Recommendation: `.scripts/git-hooks/`
- [ ] Should the hook print the user's current branch in its error message ("you're on `xyz`, push that instead")? Yes, small UX improvement — add to the script

## Relationship to other PRDs

- **PR #18 / PR #19** — the merges that triggered the incident this PRD prevents
- **PRD-217** (process lock) — same defense-in-depth pattern (local enforcement + clear error message)
- **PRD-530** (CI setup) — the GitHub branch protection rule will eventually require the CI status check to pass; until then it just requires "PR exists"
- **PRD-224** (harness invariants) — broader theme of "make wrong actions impossible, not discouraged"

## Why this is small

This is a **30-minute task**. Two short shell scripts, an installer, a README paragraph, a manual GitHub setting. No new Python code, no test infrastructure, no design decisions. The main reason it gets its own PRD instead of being a drive-by commit is that the README change + the manual GH setup are the kind of thing that's easy to forget — having a PRD makes the work visible and tracked.
