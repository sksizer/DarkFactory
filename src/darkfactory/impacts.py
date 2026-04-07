"""File impact tracking and overlap detection.

Each PRD can declare an ``impacts`` list of glob patterns naming files it
will create, modify, or delete. The harness uses these declarations to:

- Detect implicit dependencies between PRDs that touch the same files
- Decide whether sibling DAG nodes can run in parallel safely
- Surface conflicts in ``prd validate`` and ``prd conflicts <PRD>``

## Containment-aware impact model

Impact declarations obey a strict leaf-only rule:

- **Leaf PRDs** (no children in the containment tree) declare their own
  impacts via the ``impacts: [...]`` frontmatter field.
- **Container PRDs** (epics or features with descendants) MUST have
  ``impacts: []``. Their effective impact set is computed as the union
  of all *leaf* descendants' declared impacts. ``prd validate`` emits a
  hard error if a container declares non-empty impacts.

This gives a single source of truth: authors maintain one list per
leaf, and the container-level surface area is always correct by
construction. Containers can never drift from their children.

Empty impacts on a leaf means "undeclared". The overlap check treats
undeclared as "no known overlap" (so parallel execution isn't blocked
just because someone forgot to fill in the field); ``validate`` may
warn about it separately.

## Parent/child exemption

Overlap detection skips pairs where one PRD contains the other via the
containment tree. A container's effective impacts include its children
by definition, so the "overlap" is expected — not a conflict. Only
cross-tree or sibling overlaps produce warnings.
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from . import containment
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


def effective_impacts(prd: PRD, prds: dict[str, PRD]) -> list[str]:
    """Return the effective impact patterns for a PRD.

    The effective set depends on whether ``prd`` is a leaf or a container
    in the containment tree:

    - **Leaf** (no children): returns ``prd.impacts`` as declared. An
      empty list means the author hasn't filled in impacts yet.
    - **Container** (has children): returns the sorted union of all
      leaf descendants' declared impacts. Intermediate containers
      contribute through their own descendants, but are not expected
      to declare anything of their own.

    Raises ``ValueError`` if a container PRD has non-empty declared
    impacts — that's a tree consistency violation and should have been
    caught by ``prd validate`` before reaching this function. The raise
    is defensive (belt and suspenders): if a buggy caller bypasses the
    validator, the error surfaces here rather than silently producing
    the wrong answer.
    """
    direct_children = containment.children(prd.id, prds)
    if not direct_children:
        # Leaf: declared impacts are authoritative.
        return list(prd.impacts)

    # Container: must have empty declared impacts.
    if prd.impacts:
        raise ValueError(
            f"{prd.id} is a container (has {len(direct_children)} children) "
            f"but declares impacts={prd.impacts!r}. Containers must have "
            "impacts: []; their effective impact set is computed from "
            "leaf descendants. This should have been caught by `prd validate`."
        )

    # Aggregate from leaf descendants only. Intermediate containers
    # contribute through their own leaves; we walk the whole descendant
    # set and pick out the leaves.
    aggregated: set[str] = set()
    for descendant in containment.descendants(prd.id, prds):
        if not containment.children(descendant.id, prds):
            # This descendant is a leaf; include its declared impacts.
            aggregated.update(descendant.impacts)
    return sorted(aggregated)


def _is_ancestor(possibly_ancestor: PRD, child: PRD, prds: dict[str, PRD]) -> bool:
    """True if ``possibly_ancestor`` appears anywhere in ``child``'s parent chain."""
    for ancestor in containment.ancestors(child.id, prds):
        if ancestor.id == possibly_ancestor.id:
            return True
    return False


def impacts_overlap(
    a: PRD, b: PRD, files: list[str], prds: dict[str, PRD]
) -> set[str]:
    """Files both PRDs would touch.

    Returns an empty set in three cases:

    1. Either PRD's effective impacts are empty (undeclared or a
       container with no decomposed children yet).
    2. One PRD is an ancestor of the other via the containment tree
       — a parent's effective impacts include its children by
       definition, so the "overlap" isn't a conflict.
    3. The expanded impact file sets have no intersection.

    Uses :func:`effective_impacts` under the hood so containers
    automatically participate correctly (aggregated from descendants).
    """
    # Parent/child exemption: containment is not conflict.
    if _is_ancestor(a, b, prds) or _is_ancestor(b, a, prds):
        return set()

    a_patterns = effective_impacts(a, prds)
    b_patterns = effective_impacts(b, prds)
    if not a_patterns or not b_patterns:
        return set()
    return expand_impacts(a_patterns, files) & expand_impacts(b_patterns, files)


def find_conflicts(
    prd: PRD, prds: dict[str, PRD], repo_root: Path
) -> list[tuple[str, set[str]]]:
    """Return ``[(other_id, overlapping_files), ...]`` for every overlap.

    Walks every other PRD in the set and reports which files would be
    touched by both. Respects the containment-aware rules in
    :func:`impacts_overlap` — parent/child pairs are skipped, and
    container impacts are computed from their descendants.
    """
    files = tracked_files(repo_root)
    conflicts: list[tuple[str, set[str]]] = []
    for other in prds.values():
        if other.id == prd.id:
            continue
        overlap = impacts_overlap(prd, other, files, prds)
        if overlap:
            conflicts.append((other.id, overlap))
    conflicts.sort(key=lambda pair: parse_id_sort_key(pair[0]))
    return conflicts
