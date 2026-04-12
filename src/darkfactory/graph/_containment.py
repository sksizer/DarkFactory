"""Containment tree operations.

The containment relationship is encoded in each PRD's ``parent`` field
(a single PRD id or None). The whole set forms a forest: each PRD has at
most one parent, and there can be multiple roots. This is orthogonal to
the dependency DAG (``depends_on``/``blocks``).
"""

from __future__ import annotations

from collections.abc import Mapping

from ..model import PRD, parse_id_sort_key


def children(prd_id: str, prds: Mapping[str, PRD]) -> list[PRD]:
    """Direct children of ``prd_id`` (PRDs whose ``parent`` matches), naturally sorted."""
    matched = [p for p in prds.values() if p.parent == prd_id]
    matched.sort(key=lambda p: parse_id_sort_key(p.id))
    return matched


def descendants(prd_id: str, prds: Mapping[str, PRD]) -> list[PRD]:
    """All transitive children, BFS order."""
    out: list[PRD] = []
    queue = children(prd_id, prds)
    while queue:
        node = queue.pop(0)
        out.append(node)
        queue.extend(children(node.id, prds))
    return out


def ancestors(prd_id: str, prds: Mapping[str, PRD]) -> list[PRD]:
    """Walk up the parent chain. Returns parents in order from immediate to root."""
    out: list[PRD] = []
    seen: set[str] = set()
    current = prds.get(prd_id)
    while current and current.parent and current.parent not in seen:
        seen.add(current.parent)
        parent = prds.get(current.parent)
        if parent is None:
            break
        out.append(parent)
        current = parent
    return out


def roots(prds: Mapping[str, PRD]) -> list[PRD]:
    """Top-level PRDs (no parent), naturally sorted."""
    rs = [p for p in prds.values() if p.parent is None]
    rs.sort(key=lambda p: parse_id_sort_key(p.id))
    return rs


def is_leaf(prd: PRD, prds: Mapping[str, PRD]) -> bool:
    """True if ``prd`` has no children."""
    return not children(prd.id, prds)


def is_fully_decomposed(prd: PRD, prds: Mapping[str, PRD]) -> bool:
    """True if ``prd`` has at least one ``task``-kind descendant.

    An epic or feature with no task descendants is considered not yet
    decomposed and is a candidate for the planning workflow.
    """
    return any(d.kind == "task" for d in descendants(prd.id, prds))


def is_partially_decomposed(prd: PRD, prds: Mapping[str, PRD]) -> bool:
    """True if the PRD has at least one task descendant but is not marked complete.

    Heuristic: True if has task descendants AND the parent has not
    been explicitly marked complete via a frontmatter flag
    ``decomposition: complete``. False if the flag is set OR if there
    are zero task descendants (initial planning's territory).
    """
    descendants_list = descendants(prd.id, prds)
    has_tasks = any(d.kind == "task" for d in descendants_list)
    if not has_tasks:
        return False  # zero children — initial planning handles this
    fm = prd.raw_frontmatter or {}
    if fm.get("decomposition") == "complete":
        return False  # explicitly marked complete by author
    return True


def is_runnable(prd: PRD, prds: Mapping[str, PRD]) -> bool:
    """True if ``prd`` can be executed by an implementation workflow.

    A PRD is runnable when it is itself a task OR a leaf in the containment
    tree (no children to delegate to). Epics and features with children are
    NOT runnable; they are decomposed via the planning workflow instead.
    """
    if prd.kind == "task":
        return True
    return is_leaf(prd, prds)
