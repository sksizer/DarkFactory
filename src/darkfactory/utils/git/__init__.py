"""Git subprocess helpers for DarkFactory.

Public API:

Primitives (from _ops):
- :func:`git_check` — silent returncode probe
- :func:`git_run` — run git, raise on non-zero exit
- :func:`git_probe` — timeout-bounded probe for network operations
- :func:`resolve_commit_timestamp` — resolve commit SHA to ISO-8601 timestamp

Diff helpers (from _diff):
- :func:`diff_quiet` — True if no changes
- :func:`diff_show` — print colored diff to terminal

Staging helpers (from _staging):
- :func:`run_add` — stage specific files
- :func:`run_commit` — create a commit
- :func:`status_other_dirty` — list dirty files outside a given set
"""

from ._diff import diff_quiet, diff_show
from ._ops import git_check, git_probe, git_run, resolve_commit_timestamp
from ._staging import run_add, run_commit, status_other_dirty

__all__ = [
    "diff_quiet",
    "diff_show",
    "git_check",
    "git_probe",
    "git_run",
    "resolve_commit_timestamp",
    "run_add",
    "run_commit",
    "status_other_dirty",
]
