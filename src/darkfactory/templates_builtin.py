"""Built-in WorkflowTemplate definitions.

This module provides the canonical template instances that ship with
darkfactory. Import them directly rather than constructing ad-hoc
WorkflowTemplate objects in workflow definitions.
"""

from __future__ import annotations

from .templates import WorkflowTemplate
from .workflow import AgentTask, BuiltIn, ShellTask

SYSTEM_OPERATION_TEMPLATE = WorkflowTemplate(
    name="system-operation",
    description="System operation lifecycle: lock, execute, report, unlock.",
    open=[
        BuiltIn("acquire_global_lock"),
        BuiltIn("log_operation_start"),
    ],
    middle_kinds=[AgentTask, ShellTask],
    middle_required={},
    close=[
        BuiltIn("write_report"),
        BuiltIn("log_operation_end"),
        BuiltIn("release_global_lock"),
    ],
)
