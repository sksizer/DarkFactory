"""Built-in (system) workflows bundled with the darkfactory package.

Each subdirectory here is a first-party workflow (``default``, ``extraction``,
``planning``, …) discovered by :func:`darkfactory.loader.load_workflows`
alongside any user- or project-level workflows.
"""

from __future__ import annotations

from darkfactory.loader import builtin_workflows_dir, load_workflows
from darkfactory.workflow import Workflow


def get_builtin_workflows() -> dict[str, Workflow]:
    """Load all built-in workflows shipped with the package.

    Respects the ``DARKFACTORY_BUILTINS_DIR`` environment variable
    override so test suites can point at an empty directory and avoid
    collisions with real bundled workflows.
    """
    return load_workflows(builtin_workflows_dir(), include_builtins=False)
