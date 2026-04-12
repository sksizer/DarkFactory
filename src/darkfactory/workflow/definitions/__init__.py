"""Built-in workflows and project operations bundled with the darkfactory package.

Each subdirectory under ``prd/`` is a first-party workflow (``default``,
``extraction``, ``planning``, …) and each subdirectory under ``project/``
is a first-party project operation (``plan``, ``audit-impacts``, …).

Discovered by :func:`darkfactory.loader.load_workflows` and
:func:`darkfactory.loader.load_operations` alongside any user- or
project-level definitions.
"""

from __future__ import annotations

from darkfactory.loader import (
    builtin_operations_dir,
    builtin_workflows_dir,
    load_operations,
    load_workflows,
)
from darkfactory.project import ProjectOperation
from darkfactory.workflow import Workflow


def get_builtin_workflows() -> dict[str, Workflow]:
    """Load all built-in workflows shipped with the package.

    Respects the ``DARKFACTORY_BUILTINS_DIR`` environment variable
    override so test suites can point at an empty directory and avoid
    collisions with real bundled workflows.
    """
    return load_workflows(builtin_workflows_dir(), include_builtins=False)


def get_builtin_operations() -> dict[str, ProjectOperation]:
    """Load all built-in project operations shipped with the package.

    Respects the ``DARKFACTORY_BUILTINS_OPERATIONS_DIR`` environment
    variable override so test suites can point at an empty directory.
    """
    return load_operations(
        builtin_operations_dir(), include_builtins=False, include_user=False
    )
