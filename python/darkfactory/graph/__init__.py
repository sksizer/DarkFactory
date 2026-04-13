"""Graph operations: dependency DAG, containment tree, impact analysis, and execution.

Submodules:

- :mod:`~darkfactory.graph._dag` — dependency DAG build, sort, cycle detection
- :mod:`~darkfactory.graph._containment` — parent/child containment tree
- :mod:`~darkfactory.graph._impacts` — file impact tracking and overlap detection
- :mod:`~darkfactory.graph._assign` — workflow assignment resolution
- :mod:`~darkfactory.graph._execution` — sequential DAG walker for ``prd run``
"""

from __future__ import annotations

# Re-export submodules under their original public names so that
# ``from darkfactory.graph import containment`` works.
from . import _assign as assign
from . import _containment as containment
from . import _impacts as impacts

# Re-export _dag public names at package level (callers used
# ``graph.build_graph()``, ``graph.Graph``, etc.).
from ._dag import (
    Graph,
    build_graph,
    detect_cycles,
    is_actionable,
    missing_deps,
    reverse_graph,
    topological_sort,
    transitive_blocks,
)

# Re-export _execution public names at package level.
from ._execution import (
    CandidateStrategy,
    EventSink,
    ExecutionReport,
    ExecutionSlice,
    MultiDepUnsupported,
    QueueFilters,
    QueueStrategy,
    RootedStrategy,
    RunEvent,
    actionable_order,
    deps_satisfied,
    discover_ready_queue,
    execute_graph,
    graph_scope,
    matches_filters,
    plan_execution,
    resolve_base_ref,
    topo_sort_with_tiebreak,
)

# Re-export assign public names.
from ._assign import assign_all, assign_workflow

__all__ = [
    # submodules
    "assign",
    "containment",
    "impacts",
    # _dag
    "Graph",
    "build_graph",
    "detect_cycles",
    "is_actionable",
    "missing_deps",
    "reverse_graph",
    "topological_sort",
    "transitive_blocks",
    # _execution
    "CandidateStrategy",
    "EventSink",
    "ExecutionReport",
    "ExecutionSlice",
    "MultiDepUnsupported",
    "QueueFilters",
    "QueueStrategy",
    "RootedStrategy",
    "RunEvent",
    "actionable_order",
    "deps_satisfied",
    "discover_ready_queue",
    "execute_graph",
    "graph_scope",
    "matches_filters",
    "plan_execution",
    "resolve_base_ref",
    "topo_sort_with_tiebreak",
    # _assign
    "assign_all",
    "assign_workflow",
]
