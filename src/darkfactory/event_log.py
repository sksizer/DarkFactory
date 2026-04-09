"""Unified structured event log for harness execution.

Provides :class:`EventWriter`, a per-PRD JSONL writer that emits
structured events with flat correlation fields (``session_id``,
``prd_id``, ``scope``, ``type``). One file per PRD execution attempt,
stored at ``.darkfactory/events/`` in the repo root.

Events are append-only, flushed after each write, and designed for
post-mortem analysis with ``jq``. The flat-field design (no spans)
prepares for parallel execution (PRD-551) where every event must be
self-describing.

See PRD-566 for the full event catalog and design rationale.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def generate_session_id() -> str:
    """Generate a unique session identifier for a CLI invocation.

    Format: ``s-YYYYMMDD-HHMMSS-XXXX`` where XXXX is a short random hex suffix.
    """
    import secrets

    now = datetime.now(tz=timezone.utc)
    return f"s-{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


def _now_iso() -> str:
    """ISO-8601 timestamp with millisecond precision."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class EventWriter:
    """Per-PRD JSONL event writer with flat correlation fields.

    Each ``emit()`` call writes one JSON line with standard envelope
    fields (``ts``, ``session_id``, ``prd_id``, ``scope``, ``type``)
    plus any caller-supplied fields. The file is flushed after every
    write so events are visible immediately during long-running tasks.

    Thread-safe for a single PRD (one writer per PRD). Multiple writers
    for different PRDs can operate concurrently without contention.
    """

    def __init__(self, repo_root: Path, session_id: str, prd_id: str) -> None:
        self.repo_root = repo_root
        self.session_id = session_id
        self.prd_id = prd_id
        self._lock = threading.Lock()

        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        events_dir = repo_root / ".darkfactory" / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        self._path = events_dir / f"{prd_id}-{ts}.jsonl"
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, scope: str, type: str, **fields: object) -> None:
        """Append one event line with envelope fields auto-populated."""
        record: dict[str, object] = {
            "ts": _now_iso(),
            "session_id": self.session_id,
            "prd_id": self.prd_id,
            "scope": scope,
            "type": type,
        }
        record.update(fields)
        line = json.dumps(record, default=str) + "\n"
        with self._lock:
            self._file.write(line)
            self._file.flush()

    def close(self) -> None:
        """Flush and close the file handle."""
        with self._lock:
            if not self._file.closed:
                self._file.flush()
                self._file.close()

    def __enter__(self) -> EventWriter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
