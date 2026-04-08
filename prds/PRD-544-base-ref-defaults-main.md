---
id: PRD-544
title: prd run base_ref must default to main, not the current branch
kind: task
status: ready
priority: high
effort: xs
capability: trivial
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/cli.py
  - tests/test_cli_run.py
workflow:
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - reliability
  - bug
---

# `prd run` base_ref must default to `main`, not the current branch

## Summary

`_resolve_base_ref` in `src/darkfactory/cli.py` currently defaults to the **current branch** (`git rev-parse --abbrev-ref HEAD`) when no explicit `--base` is supplied. That means running `prd run PRD-X --execute` from a feature branch creates a worktree branched from that feature branch instead of `main`. The downstream effects are confusing and have already broken several runs:

1. The PRD's worktree branch carries unrelated commits from the feature branch the user happened to be on
2. `gh pr create --base <feature-branch>` either fails (the base branch doesn't exist on origin yet) or opens a stacked PR the user didn't intend
3. The PRD's branch can't merge cleanly into `main` until the parent feature branch lands
4. Diagnosing "why is this PR base wrong" requires staring at the runner's code and the git history of three branches

The fix is one line: change the default from "current HEAD" to `"main"` (with `git rev-parse --verify --quiet refs/heads/main` first to handle repos that use `master` or another default branch). The override behavior via `--base` stays exactly as today.

## Motivation

### The incident

PRD-224's planning run on 2026-04-08 surfaced this clearly:

- User was on `prd/PRD-543-harness-pr-creation-hardening` at the time
- Ran `prd run PRD-224 --execute` from `~/Developer/DarkFactory`
- Runner called `_resolve_base_ref(None, repo_root)` which returned `prd/PRD-543-harness-pr-creation-hardening`
- Worktree was created with `base_ref=prd/PRD-543-...`
- All steps through `push_branch` succeeded
- `create_pr` failed with `gh pr create --base prd/PRD-543-... ... returned non-zero exit status 1`
- The "base prd/PRD-543" was the smoking gun, but only after digging through `git worktree list` did it become clear what had happened

This is the second confirmed instance of this bug confusing a real run. It will keep happening as long as the default is "current HEAD."

### Why "current HEAD as default" is the wrong intent

The original comment in `_resolve_base_ref` says:

> the idea being that a `run-chain` starts from whatever branch the user is sitting on

That's reasonable for the **`run-chain`** case (which doesn't exist yet — see PRD-220) where you intentionally stack PRDs on a chain of feature branches. But the **single-PRD `prd run`** case, which is the only thing that exists today, almost always wants to base on `main`. PRDs are independent units of work; they should land directly into `main` unless you say otherwise.

A reasonable defaults principle: **the harness's defaults should reflect what users want 95% of the time, not the rare opt-in stacking case.** Stacking is the exception; mainline branching is the rule.

## Requirements

1. `_resolve_base_ref(explicit: str | None, repo_root: Path) -> str` defaults to `"main"` when:
   - No `--base` flag is supplied
   - No environment variable override is supplied
2. The function still uses `--base` when supplied (unchanged)
3. If `main` doesn't exist locally (rare — repos that use `master` or another default), try `master` next, then fall back to `git symbolic-ref refs/remotes/origin/HEAD` to discover the remote's default branch
4. The function does NOT consult `git rev-parse --abbrev-ref HEAD` anymore — the user's current branch is irrelevant to where a new PRD should base
5. Update the inline comment to match the new behavior
6. The `prd plan` and `prd run` output prints `base ref: main` (or whatever was resolved) so the user sees what's happening — that already works, no change needed
7. Tests cover: default returns `main`, explicit override returns the override, fallback to `master` when main is missing, fallback to `origin/HEAD` when neither exists
8. Add an environment variable escape hatch `DARKFACTORY_BASE_REF` for power users who want to default differently without typing `--base` every time
9. **When the user is on a non-default branch AND has not passed `--base`, the harness emits a clear, colored warning** before starting the run. The warning must:
   - Use the existing color/icon styling from PRD-541 (yellow / warning glyph)
   - Name the user's current branch
   - Name the resolved base ref (`main` in the common case)
   - Tell the user how to opt into stacking on their current branch instead: `Pass --base <current-branch> if you intended to stack on your current branch.`
   - Print to stderr, not stdout, so it doesn't pollute scripted output
   - Appear before any worktree creation or other side effects, so the user has a chance to Ctrl-C
10. The warning is suppressed when the user explicitly passed `--base` (any value) — they've already made the choice deliberately
11. The warning is also suppressed when the user is on `main` / `master` / whatever the default branch resolved to (no warning needed when current branch matches base)
12. The warning is suppressed in `prd plan` (dry-run) mode, since plan output already shows `base ref:` explicitly — duplicating it as a warning is noise. Or alternatively: keep the warning in plan mode too since it's what the user would see on `--execute`. **Recommendation**: keep it in plan mode, consistency wins

## Technical Approach

```python
# src/darkfactory/cli.py

def _resolve_base_ref(explicit: str | None, repo_root: Path) -> str:
    """Determine the git base ref for a new workflow branch.

    Resolution order:

    1. ``explicit`` from ``--base`` (highest priority)
    2. ``DARKFACTORY_BASE_REF`` environment variable
    3. ``main`` if it exists locally
    4. ``master`` if it exists locally
    5. The remote's default branch via ``origin/HEAD``
    6. Last resort: ``main`` (callers will hit a real error later if it's
       missing too)

    The user's current branch is **not** consulted. PRDs are independent
    units of work and should base on the project's default branch unless
    the user says otherwise. Stacking onto a feature branch is the
    exception, not the rule, and requires an explicit ``--base`` flag.
    """
    if explicit:
        return explicit

    env_override = os.environ.get("DARKFACTORY_BASE_REF")
    if env_override:
        return env_override

    for candidate in ("main", "master"):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return candidate

    # Try remote's default branch (e.g. for fresh clones with no local main)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        # Output looks like "refs/remotes/origin/main"
        return result.stdout.strip().rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass

    return "main"
```

The change is bounded to one function. No callers need updating — they all already accept whatever string `_resolve_base_ref` returns.

### The on-foreign-branch warning

A new helper that runs during `prd run` / `prd plan` setup, after `_resolve_base_ref` returns:

```python
def _warn_if_on_foreign_branch(
    explicit_base: str | None,
    resolved_base: str,
    repo_root: Path,
    *,
    logger: logging.Logger,
) -> None:
    """Warn loudly if the user is on a branch other than the resolved base.

    Suppressed when:
    - The user passed --base explicitly (they made the choice deliberately)
    - The current branch IS the resolved base (no surprise)
    - We can't determine the current branch (degraded gracefully)

    The warning is colored using the same style helpers from PRD-541
    (yellow / ⚠ glyph). It prints to stderr so scripted output stays clean.
    """
    if explicit_base is not None:
        return

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        current = result.stdout.strip()
    except subprocess.CalledProcessError:
        return  # can't tell — be quiet

    if current == resolved_base or current == "HEAD":
        return  # detached or on the base branch — fine

    # Yellow + ⚠ via PRD-541's style helpers
    from darkfactory.style import warn_color, warn_icon

    msg = (
        f"\n{warn_icon()} {warn_color('You are on branch')} "
        f"{warn_color(repr(current), bold=True)}{warn_color(' but defaulting base to')} "
        f"{warn_color(repr(resolved_base), bold=True)}{warn_color('.')}\n"
        f"   If you intended to stack on your current branch, re-run with: "
        f"{warn_color(f'--base {current}', bold=True)}\n"
    )
    print(msg, file=sys.stderr)
```

The helper is invoked from the same setup paths in `cli.py` that call `_resolve_base_ref`. It does **not** prompt or block — the user has already decided to run; the warning is informational only. If they Ctrl-C they can re-run with `--base`; otherwise the run proceeds with the safe default.

### Why warn instead of prompt?

Three reasons:

1. **Scriptability** — `prd run` should be safe to invoke from automation. A blocking prompt would break that.
2. **The default is already safe** — the warning is a "you might have wanted X" hint, not an "are you sure" gate. The action being taken is fine; we're just making the user aware of an alternative.
3. **Frequency** — most users will hit this exactly once per session (the moment they realize "oh right, I forgot to switch to main"). After they internalize the warning, it becomes informational background noise. A prompt would be obnoxious.

## Acceptance Criteria

- [ ] AC-1: Running `prd run PRD-X --execute` from a feature branch (e.g. `prd/PRD-yyy`) creates a worktree based on `main`, not on `prd/PRD-yyy`
- [ ] AC-2: `prd plan PRD-X` from the same feature branch shows `base ref: main`
- [ ] AC-3: `prd run PRD-X --base prd/PRD-yyy --execute` still respects the explicit override
- [ ] AC-4: `DARKFACTORY_BASE_REF=staging prd run PRD-X --execute` uses `staging`
- [ ] AC-5: In a repo that uses `master` (no `main` branch), the default resolves to `master`
- [ ] AC-6: In a fresh clone where neither local `main` nor `master` exists, the default resolves via `origin/HEAD`
- [ ] AC-7: Unit tests cover all five resolution paths above with mocked `subprocess.run`
- [ ] AC-8: The code comment reflects the new resolution order
- [ ] AC-9: Running `prd run PRD-X --execute` from a non-default branch (no `--base`) prints a yellow ⚠ warning to stderr naming the current branch and the resolved base, plus the `--base <current-branch>` opt-in command
- [ ] AC-10: The warning is suppressed when `--base` is passed explicitly (any value)
- [ ] AC-11: The warning is suppressed when the current branch IS the resolved base (no surprise to warn about)
- [ ] AC-12: The warning prints to stderr, not stdout, so scripted output stays clean
- [ ] AC-13: The warning appears before `ensure_worktree` runs so the user has a chance to Ctrl-C before any side effects
- [ ] AC-14: Tests cover the warning paths: on foreign branch (warns), on resolved base (silent), explicit --base (silent), detached HEAD (silent)

## Open Questions

- [ ] Should the env var be `DARKFACTORY_BASE_REF` or `DARKFACTORY_DEFAULT_BASE`? The first is shorter; the second is more descriptive. Recommendation: `DARKFACTORY_BASE_REF` for parity with `DARKFACTORY_DIR` (PRD-222's planned env var)
- [ ] Should there be a project-level config (`.darkfactory/config.toml`) override as well? Yes eventually — track in PRD-222.6 (config file support). For this PRD, env var is enough
- [ ] What about repos with multiple "default" branches (release branches, develop, etc.)? Out of scope — those projects should use the explicit `--base` flag or the env var

## Relationship to other PRDs

- **Caused** PR #25's rebase work (PRD-224 had to be rebased onto main because its worktree was branched from `prd/PRD-543-...`)
- **Related to PRD-543** — both came out of the same incident; PRD-543 makes `create_pr` failures legible, this PRD prevents one of the most common reasons it fails
- **Will eventually be replaced by** PRD-222.6's config file support (config can override the default), but the env var + flag stay as the immediate-priority overrides
- **Smaller than but related to PRD-220** — graph execution / run-chain may want to revisit "base ref defaults" with a chain-aware variant. That's a separate problem; this PRD just fixes the single-PRD case

## Why this is xs

One function. ~30 lines of new code (with the fallback chain). ~50 lines of tests. No new tests for any other module. No new dependencies. The hardest part is making sure the test for "main doesn't exist locally" runs in an isolated git repo so it doesn't accidentally exercise the test runner's actual main branch.
