"""Backward-compatibility shim — system_runner is now part of runner.

All system operation execution is handled by the unified engine in
:mod:`darkfactory.runner`. This module re-exports the public names
that existing callers import.
"""

from __future__ import annotations

# Re-export for backward compatibility during migration.
from .builtins.system_builtins import SYSTEM_BUILTINS
from .runner import RunResult, TaskStep, _task_kind, _task_name, run_system_operation

__all__ = [
    "SYSTEM_BUILTINS",
    "RunResult",
    "TaskStep",
    "_task_kind",
    "_task_name",
    "run_system_operation",
]
