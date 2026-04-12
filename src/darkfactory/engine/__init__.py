"""Execution engine: type-keyed inter-task state and data bundles.

Re-exports the core abstractions so callers can do::

    from darkfactory.engine import PhaseState, AgentResult, PrdContext

Submodules:

- :mod:`~darkfactory.engine.phase_state` — the ``PhaseState`` registry
- :mod:`~darkfactory.engine.payloads` — frozen dataclass bundles exchanged
  between tasks via ``PhaseState``
"""

from __future__ import annotations

from .payloads import AgentResult, CandidateList, PrdContext, ReworkState
from .phase_state import PhaseState

__all__ = [
    "AgentResult",
    "CandidateList",
    "PhaseState",
    "PrdContext",
    "ReworkState",
]
