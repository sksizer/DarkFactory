"""Backward-compatibility shim — phase_state is now ``darkfactory.engine``.

All typed inter-task state lives in :mod:`darkfactory.engine`. This
module re-exports public names so existing imports keep working during
migration.
"""

from __future__ import annotations

# Re-export for backward compatibility.
from .engine.payloads import AgentResult, CandidateList, PrdContext, ReworkState
from .engine.phase_state import PhaseState

__all__ = [
    "AgentResult",
    "CandidateList",
    "PhaseState",
    "PrdContext",
    "ReworkState",
]
