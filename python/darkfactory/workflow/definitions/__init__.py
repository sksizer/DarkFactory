"""Built-in workflows and project workflows bundled with the darkfactory package.

Each subdirectory under ``prd/`` is a first-party PRD workflow (``default``,
``extraction``, ``planning``, ...) and each subdirectory under ``project/``
is a first-party project workflow (``plan``, ``audit-impacts``, ...).

Discovered by :func:`darkfactory.loader.load_workflows` and
:func:`darkfactory.loader.load_project_workflows` alongside any user- or
project-level definitions.
"""

from __future__ import annotations

from darkfactory.loader import (
    builtin_project_workflows_dir,
    builtin_workflows_dir,
    load_project_workflows,
    load_workflows,
)
from darkfactory.workflow import Workflow


def get_builtin_workflows() -> dict[str, Workflow]:
    """Load all built-in PRD workflows shipped with the package.

    Respects the ``DARKFACTORY_BUILTINS_DIR`` environment variable
    override so test suites can point at an empty directory and avoid
    collisions with real bundled workflows.
    """
    return load_workflows(builtin_workflows_dir(), include_builtins=False)


def get_builtin_project_workflows() -> dict[str, Workflow]:
    """Load all built-in project workflows shipped with the package.

    Respects the ``DARKFACTORY_BUILTINS_OPERATIONS_DIR`` environment
    variable override so test suites can point at an empty directory.
    """
    return load_project_workflows(
        builtin_project_workflows_dir(), include_builtins=False, include_user=False
    )
