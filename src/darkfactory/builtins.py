"""Built-in task primitives — real implementations.

Built-ins are the deterministic SDLC operations that every workflow
references by name: create a worktree, set a PRD's status, make a
commit, push a branch, open a PR. They live here (not in individual
workflow modules) because they're shared — every workflow uses the
same ``commit`` primitive, not a bespoke one.

Workflows reference built-ins by name via :class:`~darkfactory.workflow.BuiltIn`::

    BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"})

The runner looks up ``"commit"`` in :data:`BUILTINS` and calls the
registered function with the :class:`~darkfactory.workflow.ExecutionContext`
plus any formatted kwargs.

**Dry-run mode**: every built-in checks ``ctx.dry_run`` before doing
anything destructive. In dry-run, we log what we WOULD do at INFO
level and return. This is what powers ``prd plan`` and the default
``prd run`` (without ``--execute``).

**Subprocess discipline**: all shell commands use ``subprocess.run``
with an explicit argv list (never ``shell=True``), capture output,
and check the return code. Git and gh invocations go through
:func:`_run_git` and :func:`_run_gh` helpers that centralize cwd
handling and dry-run support.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

from . import prd as prd_module
from .checks import is_resume_safe
from .workflow import ExecutionContext, Status

_log = logging.getLogger(__name__)

BuiltInFunc = Callable[..., None]
"""Signature every built-in shares: takes ``ExecutionContext`` plus **kwargs, returns None.

Return value is always ``None`` — built-ins communicate results by
mutating the context (setting ``ctx.worktree_path``, ``ctx.pr_url``, etc.)
and signal failure by raising an exception. This keeps the dispatch
uniform in the runner.
"""


BUILTINS: dict[str, BuiltInFunc] = {}
"""Global registry mapping built-in name to its implementing function.

Populated at import time via the :func:`builtin` decorator. The runner
looks up names in this dict when dispatching a
:class:`~darkfactory.workflow.BuiltIn` task. Workflows never touch this
dict directly — they reference built-ins by name only.
"""


def builtin(name: str) -> Callable[[BuiltInFunc], BuiltInFunc]:
    """Decorator that registers a function in :data:`BUILTINS`.

    Rejects duplicate registrations with ``ValueError`` to catch typos
    and accidental overrides during development.
    """

    def decorator(func: BuiltInFunc) -> BuiltInFunc:
        if name in BUILTINS:
            raise ValueError(f"duplicate builtin registration for {name!r}")
        BUILTINS[name] = func
        return func

    return decorator


# ---------- internal helpers ----------


def _run(
    ctx: ExecutionContext,
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command inside ``ctx.cwd`` with dry-run support.

    In dry-run mode, logs the command at INFO level and returns a fake
    ``CompletedProcess`` with exit code 0. In live mode, runs the
    command for real and raises ``subprocess.CalledProcessError`` on
    non-zero exit when ``check=True``.

    Using an explicit argv list (not a shell string) prevents shell
    injection entirely — callers don't get to interpolate variables
    into a command line, they build the argv themselves.
    """
    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return subprocess.run(
        cmd,
        cwd=str(ctx.cwd),
        check=check,
        capture_output=capture,
        text=True,
    )


def _worktree_target(ctx: ExecutionContext) -> Path:
    """Compute the worktree path for this PRD under ``.worktrees/``.

    Separated out so tests can assert the path without a whole
    subprocess invocation.
    """
    return ctx.repo_root / ".worktrees" / f"{ctx.prd.id}-{ctx.prd.slug}"


def _branch_exists_local(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists in the local repo's refs."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _branch_exists_remote(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists on origin.

    Best-effort: returns False (and logs a warning) on timeout or any
    subprocess error so the caller can fall back to the local check.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-remote",
                "--exit-code",
                "origin",
                f"refs/heads/{branch}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "git ls-remote timed out checking remote branch %r — skipping remote check",
            branch,
        )
        return False
    except Exception as exc:
        _log.warning(
            "git ls-remote failed checking remote branch %r (%s) — skipping remote check",
            branch,
            exc,
        )
        return False
    return result.returncode == 0


_AC_LINE_RE = re.compile(r"^\s*-\s*\[\s*\]\s*(AC-\d+.*)$", re.MULTILINE)


def _extract_acceptance_criteria(body: str) -> list[str]:
    """Pull acceptance criteria lines out of a PRD body.

    Looks for the standard ``- [ ] AC-N: ...`` checkbox format.
    Returns a list of the criterion strings (without the checkbox
    prefix). Used by ``create_pr`` to build the PR body's checklist.
    """
    return [match.group(1).strip() for match in _AC_LINE_RE.finditer(body)]


def _pr_body(ctx: ExecutionContext) -> str:
    """Generate a PR body with a link to the PRD and an AC checklist."""
    prd = ctx.prd
    lines: list[str] = [
        f"Implements `{prd.path.relative_to(ctx.repo_root)}`.",
        "",
    ]

    acs = _extract_acceptance_criteria(prd.body)
    if acs:
        lines.append("## Acceptance criteria")
        lines.append("")
        for ac in acs:
            lines.append(f"- [ ] {ac}")
        lines.append("")

    lines.append("---")
    lines.append(f"Generated by the PRD harness workflow `{ctx.workflow.name}`.")
    return "\n".join(lines)


# ---------- built-in implementations ----------


@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None:
    """Create (or resume) a git worktree for this PRD.

    Target path: ``{repo_root}/.worktrees/{prd_id}-{slug}``. Branch:
    ``prd/{prd_id}-{slug}`` created from ``ctx.base_ref``. If the
    worktree already exists (previous run resumed), reuses it without
    re-creating. Sets ``ctx.worktree_path`` and ``ctx.cwd`` on success.

    In live mode, acquires a per-PRD advisory file lock at
    ``.worktrees/{prd_id}.lock`` before any mutation so two concurrent
    ``prd run`` invocations for the same PRD fail fast with a clear
    message instead of racing. The lock is auto-released by the kernel
    when the process exits; the runner also releases it explicitly at the
    end of the run (see ``_release_worktree_lock``).
    """
    worktree_path = _worktree_target(ctx)
    branch = ctx.branch_name

    if ctx.dry_run:
        # Dry-run produces no side effects, so no lock needed.
        ctx.logger.info(
            "[dry-run] git worktree add -b %s %s %s",
            branch,
            worktree_path,
            ctx.base_ref,
        )
        ctx.worktree_path = worktree_path
        ctx.cwd = worktree_path
        return

    # Acquire the lock BEFORE the resume-check or any mutation.
    # The lock file lives at .worktrees/PRD-X.lock and is per-PRD.
    lock_path = ctx.repo_root / ".worktrees" / f"{ctx.prd.id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=0)  # non-blocking
    except Timeout:
        raise RuntimeError(
            f"{ctx.prd.id} is already being worked on by another `prd run` "
            f"process (lock held on {lock_path}). If that process died, "
            f"the lock will auto-release when its file handle is reclaimed. "
            f"On a stuck lock, delete {lock_path} manually."
        ) from None

    ctx._worktree_lock = lock

    # ---- existing logic below, now lock-protected ----
    if worktree_path.exists():
        status = is_resume_safe(branch, ctx.repo_root)
        if not status.safe:
            lock.release()
            ctx._worktree_lock = None
            raise RuntimeError(status.reason)
        ctx.logger.info("resuming existing worktree: %s", worktree_path)
        ctx.worktree_path = worktree_path
        ctx.cwd = worktree_path
        return

    local_exists = _branch_exists_local(ctx.repo_root, branch)
    remote_exists = _branch_exists_remote(ctx.repo_root, branch)
    if local_exists or remote_exists:
        # Release the lock before raising so the error state is clean.
        lock.release()
        ctx._worktree_lock = None
        raise RuntimeError(
            f"branch {branch!r} already exists but worktree {worktree_path} is gone. "
            f"Run `prd cleanup {ctx.prd.id}` to release it."
        )

    # git worktree add -b <branch> <path> <base>
    # Run from the repo root, not from ctx.cwd (which may not be a git dir yet).
    subprocess.run(
        [
            "git",
            "-C",
            str(ctx.repo_root),
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            ctx.base_ref,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    ctx.worktree_path = worktree_path
    ctx.cwd = worktree_path


@builtin("set_status")
def set_status(ctx: ExecutionContext, *, to: Status) -> None:
    """Rewrite the PRD's ``status:`` frontmatter field inside the worktree.

    Targets the worktree's copy of the PRD file, never the source repo.
    The source repo's working tree must remain untouched by ``prd run`` —
    status transitions live on the PRD's worktree branch and only reach
    the source repo via PR merge (see PRD-213).

    Uses :func:`darkfactory.prd.set_status_at`, which surgically rewrites
    only the ``status:`` and ``updated:`` lines so the resulting commit
    diff is two lines, not the whole frontmatter block.
    """
    if ctx.dry_run:
        ctx.logger.info(
            "[dry-run] set status of %s: %s -> %s (worktree=%s)",
            ctx.prd.id,
            ctx.prd.status,
            to,
            ctx.worktree_path,
        )
        return

    if ctx.worktree_path is None:
        raise RuntimeError(
            "set_status requires a worktree; ensure_worktree must run first"
        )

    relative = ctx.prd.path.relative_to(ctx.repo_root)
    target = ctx.worktree_path / relative
    prd_module.set_status_at(target, to)
    # Mirror the field updates onto the in-memory PRD so subsequent
    # builtins see the new status without re-loading from disk.
    ctx.prd.status = to
    from datetime import date as _date

    ctx.prd.updated = _date.today().isoformat()


@builtin("commit")
def commit(ctx: ExecutionContext, *, message: str) -> None:
    """Stage all changes and make a commit inside the worktree.

    ``message`` is format-string expanded against the context so
    ``"chore(prd): {prd_id} start work"`` becomes
    ``"chore(prd): PRD-070 start work"``. On an empty diff, logs and
    returns without erroring — workflows can safely commit after each
    logical step without worrying about whether anything changed.
    """
    formatted = ctx.format_string(message)
    _scan_for_forbidden_attribution(
        formatted, source=f"commit message for {ctx.prd.id}"
    )

    if ctx.dry_run:
        ctx.logger.info("[dry-run] git add -A && git commit -m %r", formatted)
        return

    # Stage everything
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )

    # Check if there's anything to commit
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(ctx.cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if diff_result.returncode == 0:
        # No staged changes — skip gracefully.
        ctx.logger.info("commit skipped: no changes to commit")
        return

    # Commit
    subprocess.run(
        ["git", "commit", "-m", formatted],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@builtin("push_branch")
def push_branch(ctx: ExecutionContext) -> None:
    """Push the current branch to origin with upstream tracking.

    Runs ``git push -u origin {branch}`` inside the worktree. Required
    before :func:`create_pr` because ``gh pr create --base`` needs the
    remote to exist.
    """
    cmd = ["git", "push", "-u", "origin", ctx.branch_name]

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return

    subprocess.run(
        cmd,
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _format_tool_counts(tool_counts: dict[str, int]) -> str:
    """Format tool counts as a compact inline string, e.g. 'Read×5, Edit×3'."""
    if not tool_counts:
        return "none"
    return ", ".join(f"{name}×{count}" for name, count in sorted(tool_counts.items()))


def _format_invocations(ctx: ExecutionContext) -> str:
    """Format agent invocation count from context."""
    count = ctx.invoke_count
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    return str(count)


@builtin("summarize_agent_run")
def summarize_agent_run(ctx: ExecutionContext) -> None:
    """Aggregate tool-call counts and write a markdown summary to ctx.run_summary."""
    result = ctx.last_invoke_result
    if result is None:
        return

    lines = [
        "## Harness execution summary",
        "",
        f"- **Workflow:** {ctx.workflow.name}",
        f"- **Model:** {ctx.model or 'unknown'}",
        f"- **Agent invocations:** {_format_invocations(ctx)}",
        f"- **Tools used:** {_format_tool_counts(result.tool_counts)}",
        f"- **Sentinel:** {result.sentinel or 'none'}",
    ]
    ctx.run_summary = "\n".join(lines)


@builtin("commit_transcript")
def commit_transcript(ctx: ExecutionContext) -> None:
    """Move agent transcript to .darkfactory/transcripts/ and stage it.

    Source: ``.harness-agent-output.log`` written by the runner after each
    agent invocation. Destination:
    ``.darkfactory/transcripts/{prd_id}-{timestamp}.log``.

    Timestamps use the wall-clock at the time this builtin runs, which is
    unique enough for sequential runs. If no transcript exists (dry-run,
    or the runner didn't produce one), this is a no-op.
    """
    src = ctx.cwd / ".harness-agent-output.log"
    if not src.exists():
        ctx.logger.info("commit_transcript: no transcript found; skipping")
        return

    if ctx.dry_run:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        dest = (
            ctx.cwd / ".darkfactory" / "transcripts" / f"{ctx.prd.id}-{timestamp}.log"
        )
        ctx.logger.info("[dry-run] move %s -> %s && git add", src, dest)
        return

    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    dest = transcript_dir / f"{ctx.prd.id}-{timestamp}.log"

    shutil.move(str(src), str(dest))

    subprocess.run(["git", "add", str(dest)], cwd=str(ctx.cwd), check=True)
    ctx.logger.info("commit_transcript: staged %s", dest.relative_to(ctx.cwd))


@builtin("create_pr")
def create_pr(ctx: ExecutionContext) -> None:
    """Open a pull request via ``gh pr create``.

    Title: ``"{prd_id}: {prd_title}"``. Body: generated from the PRD's
    acceptance criteria plus a link to the PRD file. Base branch:
    ``ctx.base_ref``. On success, sets ``ctx.pr_url`` from the URL
    printed by ``gh``. The PRD file must exist at ``ctx.prd.path``
    relative to ``ctx.repo_root``.
    """
    title = f"{ctx.prd.id}: {ctx.prd.title}"
    body = _pr_body(ctx)
    if ctx.run_summary:
        body += "\n\n" + ctx.run_summary
    _scan_for_forbidden_attribution(title, source=f"PR title for {ctx.prd.id}")
    _scan_for_forbidden_attribution(body, source=f"PR body for {ctx.prd.id}")

    if ctx.dry_run:
        ctx.logger.info(
            "[dry-run] gh pr create --base %s --title %r --body <generated>",
            ctx.base_ref,
            title,
        )
        ctx.pr_url = "https://example.test/dry-run/pr/0"
        return

    # Write the body to a temp file — passing long bodies via --body
    # can hit argv limits on some systems.
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as body_file:
        body_file.write(body)
        body_path = body_file.name

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                ctx.base_ref,
                "--title",
                title,
                "--body-file",
                body_path,
            ],
            cwd=str(ctx.cwd),
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        Path(body_path).unlink(missing_ok=True)

    # gh prints the PR URL to stdout on success.
    url_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    ctx.pr_url = url_line or None


# ----- attribution lint -----
#
# The harness MUST NOT credit Claude / Anthropic in commit messages, PR
# bodies, or run summaries. Default Claude Code commit flows tack on a
# ``Co-Authored-By: Claude ...`` trailer; subagents have been observed to
# do the same inside ``retry_agent`` cycles. We detect and reject those
# patterns loudly rather than silently stripping — silent stripping masks
# the underlying agent misbehaviour we want to notice and fix.
_FORBIDDEN_ATTRIBUTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Co-Authored-By:\s*Claude", re.IGNORECASE),
    re.compile(r"Co-Authored-By:.*@anthropic\.com", re.IGNORECASE),
    re.compile(r"Generated with .{0,20}Claude Code", re.IGNORECASE),
    re.compile(r"🤖 Generated with", re.IGNORECASE),
)


def _scan_for_forbidden_attribution(text: str, *, source: str) -> None:
    """Raise ``RuntimeError`` if ``text`` contains any forbidden pattern.

    ``source`` is a human label (e.g. ``"commit PRD-544"``) included in the
    error so failures point at the offending artifact. No-op on empty text.
    """
    if not text:
        return
    for pattern in _FORBIDDEN_ATTRIBUTION_PATTERNS:
        match = pattern.search(text)
        if match:
            raise RuntimeError(
                f"forbidden attribution pattern in {source}: {match.group(0)!r}. "
                "Claude/Anthropic must never be credited in commit messages, "
                "PR bodies, or run summaries — strip the trailer and retry."
            )


@builtin("lint_attribution")
def lint_attribution(ctx: ExecutionContext) -> None:
    """Fail if any commit on the branch or the run summary credits Claude/Anthropic.

    Scans:

    - Every commit message in ``{base_ref}..HEAD`` on the current branch
    - ``ctx.run_summary`` (which feeds the PR body)

    Intended to run after the agent + verification phases and before
    ``push_branch`` / ``create_pr``, so violations abort the workflow
    before anything lands on the remote or in a PR. Dry-run is a no-op
    because there are no real commits to scan.
    """
    if ctx.dry_run:
        ctx.logger.info("[dry-run] lint_attribution: skipped")
        return

    _scan_for_forbidden_attribution(
        ctx.run_summary or "", source=f"run summary for {ctx.prd.id}"
    )

    result = subprocess.run(
        ["git", "log", f"{ctx.base_ref}..HEAD", "--format=%H%x00%B%x1e"],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    # Record separator \x1e between commits; field separator \x00 between
    # sha and body. Keeps us robust against newlines in commit messages.
    for entry in result.stdout.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        sha, _, body = entry.partition("\x00")
        _scan_for_forbidden_attribution(
            body, source=f"commit {sha[:12]} on {ctx.branch_name}"
        )

    ctx.logger.info("lint_attribution: clean")


@builtin("cleanup_worktree")
def cleanup_worktree(ctx: ExecutionContext) -> None:
    """Remove the worktree after a successful run.

    Idempotent — if the worktree is already gone, logs and returns.
    Normally skipped during chain execution so downstream worktrees
    can base on this branch; called explicitly via ``prd cleanup``
    after the whole chain is done.
    """
    if ctx.worktree_path is None:
        ctx.logger.info("cleanup_worktree: no worktree path set, skipping")
        return

    if not ctx.worktree_path.exists():
        ctx.logger.info(
            "cleanup_worktree: %s already gone, skipping", ctx.worktree_path
        )
        return

    cmd = [
        "git",
        "-C",
        str(ctx.repo_root),
        "worktree",
        "remove",
        str(ctx.worktree_path),
    ]

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", " ".join(cmd))
        return

    subprocess.run(cmd, check=True, capture_output=True, text=True)
