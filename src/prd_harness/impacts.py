"""File impact tracking and overlap detection.

Each PRD can declare an ``impacts`` list of glob patterns naming files it
will create, modify, or delete. The harness uses these declarations to:

- Detect implicit dependencies between PRDs that touch the same files
- Decide whether sibling DAG nodes can run in parallel safely
- Surface conflicts in ``prd validate`` and ``prd conflicts <PRD>``

Empty impacts means the PRD has not declared its file impacts. Such PRDs
are treated as having no known overlap (they will not block parallel runs)
but ``validate`` emits a warning suggesting the author fill the field in.
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from .prd import PRD, parse_id_sort_key


def tracked_files(repo_root: Path) -> list[str]:
    """Return all git-tracked files as repo-relative POSIX paths."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=True,
    )
    return [line for line in result.stdout.strip().split("\n") if line]


_GLOB_META = set("*?[{")


def _is_glob(pattern: str) -> bool:
    """True if the pattern contains glob metacharacters."""
    return any(c in _GLOB_META for c in pattern)


def expand_impacts(patterns: list[str], files: list[str]) -> set[str]:
    """Expand glob patterns against a file list, returning matched paths.

    Literal (non-glob) patterns are included verbatim even if the file
    doesn't exist yet — this lets a PRD declare impacts on files it plans
    to create. Glob patterns are matched against the existing file list
    and only produce matches for files that already exist.

    This split matters for overlap detection: two PRDs declaring the same
    new file (e.g. ``src/foo.rs``) should be flagged as conflicting even
    before either one runs.
    """
    matched: set[str] = set()
    for pattern in patterns:
        if _is_glob(pattern):
            # Glob pattern: expand against existing files only.
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    matched.add(f)
        else:
            # Literal path: include verbatim, even if not yet tracked.
            matched.add(pattern)
    return matched


def impacts_overlap(a: PRD, b: PRD, files: list[str]) -> set[str]:
    """Files both PRDs would touch.

    Returns an empty set when either side has undeclared (empty) impacts —
    we treat undeclared as "no known overlap" so it doesn't block parallel
    execution. The validator warns separately about undeclared impacts.
    """
    if not a.impacts or not b.impacts:
        return set()
    return expand_impacts(a.impacts, files) & expand_impacts(b.impacts, files)


def find_conflicts(
    prd: PRD, prds: dict[str, PRD], repo_root: Path
) -> list[tuple[str, set[str]]]:
    """Return ``[(other_id, overlapping_files), ...]`` for every overlap."""
    files = tracked_files(repo_root)
    conflicts: list[tuple[str, set[str]]] = []
    for other in prds.values():
        if other.id == prd.id:
            continue
        overlap = impacts_overlap(prd, other, files)
        if overlap:
            conflicts.append((other.id, overlap))
    conflicts.sort(key=lambda pair: parse_id_sort_key(pair[0]))
    return conflicts
