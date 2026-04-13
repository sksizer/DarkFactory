"""Loop detection for the rework workflow.

Tracks consecutive no-change rework attempts per PRD. When a rework
cycle produces no changes, the counter increments. After N consecutive
no-change cycles (default 2), the PRD is blocked from further automatic
rework until manual intervention resets the guard.

State persists in ``.darkfactory/state/rework-guard.json`` so the guard
survives process restarts and is visible to the rework-watch daemon.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("darkfactory.rework.guard")

DEFAULT_MAX_CONSECUTIVE: int = 2
_STATE_RELPATH = Path(".darkfactory") / "state" / "rework-guard.json"


@dataclass
class GuardOutcome:
    """Result of recording a rework cycle outcome."""

    blocked: bool
    """True if the PRD is now blocked from further automatic rework."""

    consecutive_no_change: int
    """Number of consecutive no-change cycles after this recording."""

    warning: str | None = field(default=None)
    """Human-readable warning message, or None when no warning is needed."""


class ReworkGuard:
    """Manages loop detection state for the rework workflow.

    State is stored per-PRD in a JSON file at
    ``repo_root / .darkfactory/state/rework-guard.json``. The file is
    read fresh on every call so multiple processes see consistent state.

    Typical use::

        guard = ReworkGuard(repo_root)

        # After each rework cycle:
        outcome = guard.record_outcome(prd_id, had_changes=had_changes)
        if outcome.blocked:
            raise RuntimeError(outcome.warning)

        # Before starting a rework cycle (e.g. from the watcher):
        if guard.is_blocked(prd_id):
            skip()
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        max_consecutive: int = DEFAULT_MAX_CONSECUTIVE,
        state_path: Path = _STATE_RELPATH,
    ) -> None:
        self.repo_root = repo_root
        self.max_consecutive = max_consecutive
        self._state_file = repo_root / state_path

    @property
    def state_file(self) -> Path:
        """Absolute path to the guard state file."""
        return self._state_file

    def is_blocked(self, prd_id: str) -> bool:
        """Return True if ``prd_id`` is blocked from further automatic rework."""
        state = self._load()
        entry = state.get(prd_id, {})
        return bool(entry.get("blocked", False))

    def get_consecutive_no_change(self, prd_id: str) -> int:
        """Return the current consecutive no-change count for ``prd_id``."""
        state = self._load()
        entry = state.get(prd_id, {})
        raw = entry.get("consecutive_no_change")
        return raw if isinstance(raw, int) else 0

    def record_outcome(self, prd_id: str, *, had_changes: bool) -> GuardOutcome:
        """Record the outcome of a rework cycle and return the guard result.

        If ``had_changes`` is True, resets the consecutive counter and
        unblocks the PRD. If False, increments the counter and blocks
        when the threshold is reached.
        """
        state = self._load()
        entry: dict[str, object] = state.get(
            prd_id, {"consecutive_no_change": 0, "blocked": False}
        )

        if had_changes:
            entry["consecutive_no_change"] = 0
            entry["blocked"] = False
            state[prd_id] = entry
            self._save(state)
            return GuardOutcome(blocked=False, consecutive_no_change=0)

        # No changes — increment counter.
        raw = entry.get("consecutive_no_change")
        count = (raw if isinstance(raw, int) else 0) + 1
        entry["consecutive_no_change"] = count

        blocked = count >= self.max_consecutive
        if blocked:
            entry["blocked"] = True

        state[prd_id] = entry
        self._save(state)

        if blocked:
            warning = (
                f"{prd_id}: blocked after {count} consecutive no-change rework "
                f"cycle(s). Manual intervention required to reset "
                f"(remove entry from {self._state_file})."
            )
        else:
            warning = (
                f"{prd_id}: rework produced no changes "
                f"({count}/{self.max_consecutive} consecutive). "
                f"Will block after {self.max_consecutive} consecutive no-change cycles."
            )

        return GuardOutcome(
            blocked=blocked, consecutive_no_change=count, warning=warning
        )

    def reset(self, prd_id: str) -> None:
        """Clear the guard state for ``prd_id`` (resets block and counter)."""
        state = self._load()
        state.pop(prd_id, None)
        self._save(state)

    def _load(self) -> dict[str, dict[str, object]]:
        """Read guard state from disk. Returns empty dict if file is missing."""
        if not self._state_file.exists():
            return {}
        try:
            text = self._state_file.read_text(encoding="utf-8")
            data: dict[str, dict[str, object]] = json.loads(text)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning(
                "failed to read rework guard state from %s: %s", self._state_file, exc
            )
            return {}

    def _save(self, state: dict[str, dict[str, object]]) -> None:
        """Write guard state to disk, creating parent directories as needed."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
