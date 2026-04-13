"""Workflow package: task definitions, templates, prompt composition, and built-in workflows.

Submodules:

- :mod:`~darkfactory.workflow._core` — task types, ``Workflow``, ``RunContext``
- :mod:`~darkfactory.workflow._templates` — prompt loading and ``WorkflowTemplate``
- :mod:`~darkfactory.workflow._templates_builtin` — pre-built workflow templates
- :mod:`~darkfactory.workflow.definitions` — shipped workflow implementations
"""

from __future__ import annotations

# _core — task types, workflow container, run context
from ._core import (
    AgentTask,
    AppliesToPredicate,
    BuiltIn,
    InteractiveTask,
    OnFailure,
    RunContext,
    ShellTask,
    Status,
    Task,
    Workflow,
    _default_applies_to,
)

# _templates — prompt file loading, substitution, WorkflowTemplate
from ._templates import (
    PLACEHOLDER_RE,
    TemplateViolation,
    WorkflowTemplate,
    compose_prompt,
    load_prompt_files,
    substitute_placeholders,
)

# _templates_builtin — pre-built template instances
from ._templates_builtin import (
    EXTRACTION_TEMPLATE,
    PRD_IMPLEMENTATION_TEMPLATE,
    REWORK_TEMPLATE,
    SYSTEM_OPERATION_TEMPLATE,
)

__all__ = [
    # _core
    "AgentTask",
    "AppliesToPredicate",
    "BuiltIn",
    "InteractiveTask",
    "OnFailure",
    "RunContext",
    "ShellTask",
    "Status",
    "Task",
    "Workflow",
    "_default_applies_to",
    # _templates
    "PLACEHOLDER_RE",
    "TemplateViolation",
    "WorkflowTemplate",
    "compose_prompt",
    "load_prompt_files",
    "substitute_placeholders",
    # _templates_builtin
    "EXTRACTION_TEMPLATE",
    "PRD_IMPLEMENTATION_TEMPLATE",
    "REWORK_TEMPLATE",
    "SYSTEM_OPERATION_TEMPLATE",
]
