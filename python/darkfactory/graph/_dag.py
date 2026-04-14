"""Dependency DAG operations over a PRD set.

Edges flow ``dep -> prd`` meaning "the dep must be done before this PRD can
start". The graph is built from each PRD's ``depends_on`` list. Cycle
detection uses Tarjan's strongly-connected-components algorithm.
"""

from __future__ import annotations

from ..model import PRD, parse_id_sort_key

# Adjacency: ``id -> set of ids that depend on it``.
# This is the "downstream" direction: edge ``A -> B`` means "B depends on A,
# so finishing A unblocks B".
Graph = dict[str, set[str]]


def build_graph(prds: dict[str, PRD]) -> Graph:
    """Build the downstream-edge dependency graph from a PRD set.

    Missing dep references are silently dropped here; ``validate`` reports them
    separately so the graph routines can stay total.
    """
    graph: Graph = {prd_id: set() for prd_id in prds}
    for prd in prds.values():
        for dep in prd.depends_on:
            if dep in graph:
                graph[dep].add(prd.id)
    return graph


def reverse_graph(graph: Graph) -> Graph:
    """Reverse the edge direction (``A -> B`` becomes ``B -> A``)."""
    reversed_g: Graph = {node: set() for node in graph}
    for src, dsts in graph.items():
        for dst in dsts:
            reversed_g.setdefault(dst, set()).add(src)
            reversed_g.setdefault(src, set())  # ensure src exists
    return reversed_g


def detect_cycles(graph: Graph) -> list[list[str]]:
    """Return a list of cycles found via Tarjan's SCC algorithm.

    Each entry is a list of node ids forming the cycle. A self-loop counts as
    a cycle of length 1. Acyclic graphs return ``[]``.
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[list[str]] = []

    def strongconnect(node: str) -> None:
        indices[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for successor in graph.get(node, ()):
            if successor not in indices:
                strongconnect(successor)
                lowlinks[node] = min(lowlinks[node], lowlinks[successor])
            elif successor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[successor])

        if lowlinks[node] == indices[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == node:
                    break
            # An SCC is a cycle if it has more than one node, OR if it has
            # exactly one node with a self-loop.
            if len(scc) > 1 or (len(scc) == 1 and scc[0] in graph.get(scc[0], ())):
                cycles.append(sorted(scc, key=parse_id_sort_key))

    for node in list(graph.keys()):
        if node not in indices:
            strongconnect(node)

    return cycles


def topological_sort(graph: Graph) -> list[str]:
    """Kahn's algorithm topological sort.

    Returns an ordering where each node appears after all its upstream
    dependencies. Tie-breaks by natural sort of PRD ids for determinism.
    Assumes the graph is acyclic; will raise on cycles.
    """
    in_degree: dict[str, int] = {node: 0 for node in graph}
    for src, dsts in graph.items():
        for dst in dsts:
            in_degree[dst] = in_degree.get(dst, 0) + 1
            in_degree.setdefault(src, in_degree.get(src, 0))

    ready = sorted(
        [node for node, deg in in_degree.items() if deg == 0],
        key=parse_id_sort_key,
    )
    out: list[str] = []

    while ready:
        node = ready.pop(0)
        out.append(node)
        for successor in sorted(graph.get(node, ()), key=parse_id_sort_key):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                # Insert in sorted position to maintain determinism.
                ready.append(successor)
                ready.sort(key=parse_id_sort_key)

    if len(out) != len(in_degree):
        raise ValueError("graph contains a cycle; cannot topologically sort")
    return out


def transitive_blocks(graph: Graph, root_id: str) -> list[str]:
    """BFS over downstream edges from ``root_id``, returning all reachable nodes.

    Excludes the root itself. Useful for computing the chain of PRDs that will
    become actionable as the root completes.
    """
    visited: set[str] = set()
    queue: list[str] = list(graph.get(root_id, ()))
    out: list[str] = []
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        out.append(node)
        queue.extend(graph.get(node, ()))
    return sorted(out, key=parse_id_sort_key)


def is_actionable(prd: PRD, prds: dict[str, PRD]) -> bool:
    """True if ``prd`` is ``ready`` and every dep exists and is ``done``."""
    if prd.status != "ready":
        return False
    for dep_id in prd.depends_on:
        dep = prds.get(dep_id)
        if dep is None or dep.status != "done":
            return False
    return True


def missing_deps(prd: PRD, prds: dict[str, PRD]) -> list[str]:
    """Return dep ids referenced by ``prd`` that aren't present in ``prds``."""
    return [dep_id for dep_id in prd.depends_on if dep_id not in prds]
