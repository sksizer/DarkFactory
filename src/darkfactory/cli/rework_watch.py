"""CLI subcommand: rework-watch — polling daemon that auto-triggers rework.

Polls open PRs whose head branch matches ``prd/PRD-*``, compares review
comments against the last-seen state, and runs ``prd rework PRD-X`` when
new unaddressed feedback appears.

Modes:
  foreground (default) — run poll loop in the current process
  --daemon             — fork and detach to background (writes PID file)
  --status             — print daemon status and exit
  --pause              — create the pause file and exit
  --resume             — remove the pause file and exit
  --stop               — send SIGTERM to the daemon and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time

from darkfactory.git_ops import git_run
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── File paths ──────────────────────────────────────────────────────────────

_STATE_SUBDIR = Path(".darkfactory") / "state"
_STATE_FILE = _STATE_SUBDIR / "rework-watch.json"
_PAUSE_FILE = _STATE_SUBDIR / "rework-watch.pause"
_PID_FILE = _STATE_SUBDIR / "rework-watch.pid"

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_POLL_INTERVAL = 60  # seconds
DEFAULT_MAX_REWORKS_PER_HOUR = 3
_RATE_WINDOW = 3600  # 1 hour in seconds


# ── State persistence ────────────────────────────────────────────────────────


@dataclass
class PRWatchState:
    """Per-PR watch state."""

    last_seen_comment_ids: set[str] = field(default_factory=set)
    rework_timestamps: list[float] = field(default_factory=list)  # epoch seconds


@dataclass
class WatchState:
    """Full persisted state for the rework-watch daemon."""

    prs: dict[str, PRWatchState] = field(default_factory=dict)


def _state_file(repo_root: Path) -> Path:
    return repo_root / _STATE_FILE


def _pause_file(repo_root: Path) -> Path:
    return repo_root / _PAUSE_FILE


def _pid_file(repo_root: Path) -> Path:
    return repo_root / _PID_FILE


def load_state(repo_root: Path) -> WatchState:
    """Load persisted state from disk; return empty state on any error."""
    path = _state_file(repo_root)
    if not path.is_file():
        return WatchState()
    try:
        raw: dict[str, Any] = json.loads(path.read_text())
        state = WatchState()
        for pr_key, pr_raw in raw.get("prs", {}).items():
            state.prs[pr_key] = PRWatchState(
                last_seen_comment_ids=set(pr_raw.get("last_seen_comment_ids", [])),
                rework_timestamps=list(pr_raw.get("rework_timestamps", [])),
            )
        return state
    except (json.JSONDecodeError, KeyError, TypeError):
        _log.warning("Corrupt state file %s; starting fresh", path)
        return WatchState()


def save_state(repo_root: Path, state: WatchState) -> None:
    """Persist state to disk, creating the state directory if needed."""
    path = _state_file(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"prs": {}}
    for pr_key, pr_state in state.prs.items():
        payload["prs"][pr_key] = {
            "last_seen_comment_ids": sorted(pr_state.last_seen_comment_ids),
            "rework_timestamps": pr_state.rework_timestamps,
        }
    path.write_text(json.dumps(payload, indent=2))


# ── Rate limiting ─────────────────────────────────────────────────────────────


def _prune_old_timestamps(timestamps: list[float], now: float) -> list[float]:
    """Remove timestamps older than the rate window."""
    cutoff = now - _RATE_WINDOW
    return [t for t in timestamps if t >= cutoff]


def is_rate_limited(pr_state: PRWatchState, max_per_hour: int, now: float) -> bool:
    """Return True if this PR has hit the rate cap for the current window."""
    recent = _prune_old_timestamps(pr_state.rework_timestamps, now)
    return len(recent) >= max_per_hour


def record_rework(pr_state: PRWatchState, now: float) -> None:
    """Record a rework invocation and prune stale timestamps."""
    pr_state.rework_timestamps = _prune_old_timestamps(pr_state.rework_timestamps, now)
    pr_state.rework_timestamps.append(now)


# ── PR / worktree discovery ──────────────────────────────────────────────────


def _prd_id_from_branch(branch: str) -> str | None:
    """Extract ``PRD-X`` id from a branch name like ``prd/PRD-225.6-...``."""
    m = re.match(r"^prd/(PRD-[\w.]+)-", branch)
    return m.group(1) if m else None


def fetch_open_prd_prs(repo_root: Path) -> list[dict[str, Any]]:
    """Return a list of open PRs whose head branch matches ``prd/PRD-*``.

    Each dict has keys ``number`` (int) and ``headRefName`` (str).
    Returns an empty list if ``gh`` is unavailable or fails.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--json",
                "number,headRefName",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            _log.warning("gh pr list failed: %s", result.stderr.strip())
            return []
        prs: list[dict[str, Any]] = json.loads(result.stdout)
        return [p for p in prs if re.match(r"^prd/PRD-", p.get("headRefName", ""))]
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        _log.warning("Could not fetch open PRs: %s", exc)
        return []


def _worktree_exists(prd_id: str, repo_root: Path) -> bool:
    """Return True if a git worktree for ``prd_id`` is registered."""
    try:
        result = git_run("worktree", "list", "--porcelain", cwd=repo_root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    for line in result.stdout.splitlines():
        if line.startswith("branch "):
            branch_ref = line[len("branch ") :]
            branch = branch_ref.removeprefix("refs/heads/")
            if re.match(rf"^prd/{re.escape(prd_id)}-", branch):
                return True
    return False


def check_missing_worktrees(prs: list[dict[str, Any]], repo_root: Path) -> list[str]:
    """Return PRD IDs whose worktrees are missing."""
    missing: list[str] = []
    for pr in prs:
        branch = pr.get("headRefName", "")
        prd_id = _prd_id_from_branch(branch)
        if prd_id and not _worktree_exists(prd_id, repo_root):
            missing.append(prd_id)
    return missing


# ── Comment comparison ───────────────────────────────────────────────────────


def _fetch_comment_ids(pr_number: int) -> set[str]:
    """Return the set of all comment/thread IDs for ``pr_number``."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "comments,reviews,reviewThreads",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        raw: dict[str, Any] = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        return set()

    ids: set[str] = set()
    for idx, rt in enumerate(raw.get("reviewThreads") or []):
        comments = rt.get("comments") or []
        if comments:
            cid = comments[0].get("id") or f"rt-{idx}"
            ids.add(cid)
    for idx, rev in enumerate(raw.get("reviews") or []):
        if (rev.get("body") or "").strip():
            rid = rev.get("id") or f"review-{idx}"
            ids.add(rid)
    for idx, c in enumerate(raw.get("comments") or []):
        cid = c.get("id") or f"comment-{idx}"
        ids.add(cid)
    return ids


def _has_new_unresolved_comments(
    pr_number: int,
    pr_state: PRWatchState,
) -> tuple[bool, set[str]]:
    """Return ``(has_new, all_current_ids)`` for the PR.

    Fetches current comment IDs and checks for any not in ``last_seen``.
    Also checks for unresolved threads via pr_comments module.
    """
    current_ids = _fetch_comment_ids(pr_number)
    new_ids = current_ids - pr_state.last_seen_comment_ids
    return bool(new_ids), current_ids


# ── Process lock ─────────────────────────────────────────────────────────────


def _prd_is_locked(prd_id: str, repo_root: Path) -> bool:
    """Return True if the per-PRD process lock is held by another process."""
    lock_path = repo_root / ".worktrees" / f"{prd_id}.lock"
    if not lock_path.exists():
        return False
    try:
        from filelock import FileLock

        lock = FileLock(str(lock_path))
        lock.acquire(timeout=0)
        lock.release()
        return False
    except Exception:
        return True


# ── PID file helpers ─────────────────────────────────────────────────────────


def _write_pid(repo_root: Path) -> None:
    path = _pid_file(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()))


def _read_pid(repo_root: Path) -> int | None:
    path = _pid_file(repo_root)
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def _remove_pid(repo_root: Path) -> None:
    path = _pid_file(repo_root)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _pid_is_alive(pid: int) -> bool:
    """Return True if the process with ``pid`` exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we don't own it


# ── Control-mode commands ────────────────────────────────────────────────────


def _cmd_status(repo_root: Path) -> int:
    pid = _read_pid(repo_root)
    if pid is None:
        print("rework-watch: not running (no PID file)")
        return 0
    if _pid_is_alive(pid):
        paused = _pause_file(repo_root).exists()
        state_str = "paused" if paused else "running"
        print(f"rework-watch: {state_str} (PID {pid})")
    else:
        print(f"rework-watch: stale PID {pid} (process not found)")
        _remove_pid(repo_root)
    return 0


def _cmd_pause(repo_root: Path) -> int:
    pf = _pause_file(repo_root)
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.touch()
    print("rework-watch: pause file created")
    return 0


def _cmd_resume(repo_root: Path) -> int:
    pf = _pause_file(repo_root)
    if pf.exists():
        pf.unlink()
        print("rework-watch: pause file removed")
    else:
        print("rework-watch: not paused")
    return 0


def _cmd_stop(repo_root: Path) -> int:
    pid = _read_pid(repo_root)
    if pid is None:
        print("rework-watch: no PID file (not running?)")
        return 1
    if not _pid_is_alive(pid):
        print(f"rework-watch: stale PID {pid} (process not found)")
        _remove_pid(repo_root)
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"rework-watch: sent SIGTERM to PID {pid}")
        return 0
    except ProcessLookupError:
        print(f"rework-watch: process {pid} already gone")
        _remove_pid(repo_root)
        return 1


# ── Poll loop ────────────────────────────────────────────────────────────────


def _trigger_rework(prd_id: str, data_dir: Path) -> int:
    """Run ``prd rework PRD-X --execute`` as a subprocess.

    Returns the subprocess exit code.
    """
    cmd = [sys.executable, "-m", "darkfactory.cli", "rework", prd_id, "--execute"]
    result = subprocess.run(cmd, cwd=data_dir.parent)
    return result.returncode


def run_poll_loop(
    repo_root: Path,
    data_dir: Path,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_reworks_per_hour: int = DEFAULT_MAX_REWORKS_PER_HOUR,
) -> None:
    """Main polling loop — runs until interrupted."""
    _log.info("rework-watch: starting poll loop (interval=%ds)", poll_interval)

    # Check for missing worktrees at startup
    open_prs = fetch_open_prd_prs(repo_root)
    missing = check_missing_worktrees(open_prs, repo_root)
    if missing:
        print(
            f"ERROR: rework-watch refusing to start; "
            f"missing worktrees for: {', '.join(missing)}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    state = load_state(repo_root)

    while True:
        # Pause check
        if _pause_file(repo_root).exists():
            _log.debug("rework-watch: paused — skipping poll cycle")
            time.sleep(poll_interval)
            continue

        open_prs = fetch_open_prd_prs(repo_root)
        now = time.time()

        for pr in open_prs:
            pr_number: int = pr["number"]
            branch: str = pr["headRefName"]
            prd_id = _prd_id_from_branch(branch)
            if prd_id is None:
                continue

            pr_key = str(pr_number)
            if pr_key not in state.prs:
                state.prs[pr_key] = PRWatchState()
            pr_state = state.prs[pr_key]

            has_new, current_ids = _has_new_unresolved_comments(pr_number, pr_state)

            if has_new:
                if is_rate_limited(pr_state, max_reworks_per_hour, now):
                    _log.warning(
                        "rework-watch: rate limit reached for %s (PR #%d); skipping",
                        prd_id,
                        pr_number,
                    )
                    # Still update seen IDs so we don't re-check the same comments
                    pr_state.last_seen_comment_ids = current_ids
                    continue

                if _prd_is_locked(prd_id, repo_root):
                    _log.info(
                        "rework-watch: %s is locked by another process; skipping",
                        prd_id,
                    )
                    continue

                _log.info(
                    "rework-watch: new comments on %s (PR #%d); triggering rework",
                    prd_id,
                    pr_number,
                )
                rc = _trigger_rework(prd_id, data_dir)
                if rc == 0:
                    record_rework(pr_state, now)
                    pr_state.last_seen_comment_ids = current_ids
                else:
                    _log.warning("rework-watch: rework for %s exited %d", prd_id, rc)
            else:
                # Keep seen IDs up to date even when no new comments
                pr_state.last_seen_comment_ids = current_ids

        save_state(repo_root, state)
        time.sleep(poll_interval)


# ── Entry point ───────────────────────────────────────────────────────────────


def cmd_rework_watch(args: argparse.Namespace) -> int:
    """Entry point for ``prd rework-watch``."""
    from darkfactory.cli._shared import _find_repo_root

    repo_root = _find_repo_root(args.data_dir)

    # Control modes that don't need the poll loop
    if args.status:
        return _cmd_status(repo_root)
    if args.pause:
        return _cmd_pause(repo_root)
    if args.resume:
        return _cmd_resume(repo_root)
    if args.stop:
        return _cmd_stop(repo_root)

    poll_interval: int = args.interval
    max_reworks: int = args.max_reworks

    if args.daemon:
        # Fork and detach
        pid = os.fork()
        if pid > 0:
            # Parent: wait briefly for child to write PID, then return
            print(f"rework-watch: daemon started (PID {pid})")
            return 0

        # Child: detach from terminal
        os.setsid()
        # Close stdin/stdout/stderr
        for fd in (0, 1, 2):
            try:
                os.close(fd)
            except OSError:
                pass
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)

        logging.basicConfig(level=logging.INFO)
        _write_pid(repo_root)
        try:
            run_poll_loop(repo_root, args.data_dir, poll_interval, max_reworks)
        finally:
            _remove_pid(repo_root)
        return 0

    # Foreground mode
    _write_pid(repo_root)
    try:
        run_poll_loop(repo_root, args.data_dir, poll_interval, max_reworks)
    except KeyboardInterrupt:
        print("\nrework-watch: interrupted")
    finally:
        _remove_pid(repo_root)
    return 0
