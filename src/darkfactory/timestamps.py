"""Timestamp helpers used across the harness.

Three canonical formats:

- :func:`today_iso` — calendar date (``YYYY-MM-DD``)
- :func:`now_iso_utc` — UTC millisecond ISO-8601 with ``Z`` suffix
- :func:`now_filename_safe` — filesystem-safe datetime with hyphens in the
  time part (``YYYY-MM-DDTHH-MM-SS``)
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD``."""
    return date.today().isoformat()


def now_iso_utc() -> str:
    """Return the current UTC time as an ISO-8601 string with millisecond precision.

    Format: ``YYYY-MM-DDTHH:MM:SS.mmmZ``
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def now_filename_safe() -> str:
    """Return the current local time in a filesystem-safe form.

    Format: ``YYYY-MM-DDTHH-MM-SS``  (colons replaced with hyphens so the
    string is safe in filenames on all platforms).
    """
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
