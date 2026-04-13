"""Dynamic workflow discovery.

The harness discovers workflows at runtime by scanning directories for
subdirectories that contain a ``workflow.py`` module. Each matching module
is imported and expected to expose a top-level ``workflow`` attribute.

Import errors in one module don't block the others — we log the
error and skip. Duplicate *names* across layers are a hard
``ValueError`` since they'd make the assignment logic ambiguous.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

from .workflow import Workflow

logger = logging.getLogger("darkfactory.loader")


def builtin_workflows_dir() -> Path:
    """Return the directory containing first-party (built-in) PRD workflows.

    These ship inside the installed ``darkfactory`` package at
    ``src/darkfactory/workflow/definitions/prd/`` and are available to
    every install without any on-disk setup in the target project.

    The ``DARKFACTORY_BUILTINS_DIR`` environment variable overrides the
    default — used by the test suite to point at an empty directory so
    CLI fixture tests can isolate from the real bundled workflows.
    """
    override = os.environ.get("DARKFACTORY_BUILTINS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "workflow" / "definitions" / "prd"


def builtin_project_workflows_dir() -> Path:
    """Return the directory containing first-party (built-in) project workflows.

    These ship inside the installed ``darkfactory`` package at
    ``src/darkfactory/workflow/definitions/project/``.

    The ``DARKFACTORY_BUILTINS_OPERATIONS_DIR`` environment variable
    overrides the default — used by the test suite.
    """
    override = os.environ.get("DARKFACTORY_BUILTINS_OPERATIONS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "workflow" / "definitions" / "project"


def load_workflows(
    workflows_dir: Path | None = None,
    *,
    include_builtins: bool = True,
) -> dict[str, Workflow]:
    """Discover PRD workflows across the built-in and project layers.

    Two layers are scanned:

    1. **Built-in** — bundled with the package at
       :func:`builtin_workflows_dir` (e.g. ``default``, ``extraction``,
       ``planning``). Included unless ``include_builtins=False``.
    2. **Project** — ``workflows_dir`` (typically
       ``<project>/.darkfactory/workflows/``). Optional.

    Each direct subdirectory of a layer is inspected for a ``workflow.py``
    file. When found, the module is loaded via ``importlib`` with a unique
    synthetic module name and registered in ``sys.modules`` so relative
    imports inside the workflow module resolve correctly.

    After import, the module must expose a top-level ``workflow``
    attribute that is a :class:`Workflow` instance. The loader sets
    ``workflow.workflow_dir`` to the subdirectory path so
    ``AgentTask.prompts`` paths can be resolved relative to it at
    runtime.

    A missing ``workflows_dir`` (or one that doesn't exist) is not an
    error — built-ins still load.

    Name collisions **across layers** are a hard ``ValueError`` per
    PRD-222: we prefer loud failure to silent override during the early
    period. Import errors in individual workflow modules are logged at
    WARNING level and the module is skipped; the rest of the scan
    continues.
    """
    workflows: dict[str, Workflow] = {}

    layers: list[Path] = []
    if include_builtins:
        layers.append(builtin_workflows_dir())
    if workflows_dir is not None:
        layers.append(workflows_dir)

    for layer_dir in layers:
        if not layer_dir.exists() or not layer_dir.is_dir():
            logger.debug("workflows directory not found: %s", layer_dir)
            continue

        for subdir in sorted(layer_dir.iterdir()):
            if (
                not subdir.is_dir()
                or subdir.name.startswith("_")
                or subdir.name.startswith(".")
            ):
                continue
            workflow_file = subdir / "workflow.py"
            if not workflow_file.exists():
                continue

            try:
                wf = _load_workflow_module(workflow_file, subdir)
            except Exception as exc:  # noqa: BLE001 — we want to log *any* failure
                logger.warning(
                    "failed to load workflow from %s: %s", workflow_file, exc
                )
                continue

            if wf.name in workflows:
                existing = workflows[wf.name].workflow_dir
                raise ValueError(
                    f"duplicate workflow name {wf.name!r}: "
                    f"defined in both {existing} and {subdir}"
                )
            workflows[wf.name] = wf

    return workflows


def _scan_project_workflows_layer(
    layer_dir: Path,
    workflows: dict[str, Workflow],
) -> None:
    """Scan a single layer directory for workflow.py modules (project workflows)."""
    if not layer_dir.exists() or not layer_dir.is_dir():
        logger.debug("project workflows directory not found: %s", layer_dir)
        return

    for subdir in sorted(layer_dir.iterdir()):
        if (
            not subdir.is_dir()
            or subdir.name.startswith("_")
            or subdir.name.startswith(".")
        ):
            continue

        # Support both workflow.py (new) and operation.py (legacy)
        workflow_file = subdir / "workflow.py"
        if not workflow_file.exists():
            workflow_file = subdir / "operation.py"
        if not workflow_file.exists():
            continue

        try:
            wf = _load_workflow_module(
                workflow_file, subdir, module_prefix="_darkfactory_project_workflow_"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to load project workflow from %s: %s", workflow_file, exc
            )
            continue

        if wf.name in workflows:
            existing = workflows[wf.name].workflow_dir
            raise ValueError(
                f"duplicate project workflow name {wf.name!r}: "
                f"defined in both {existing} and {subdir}"
            )
        workflows[wf.name] = wf


def load_project_workflows(
    workflows_dir: Path | None = None,
    *,
    include_builtins: bool = True,
    include_user: bool = True,
) -> dict[str, Workflow]:
    """Discover project workflows across built-in, user, and project layers.

    Three layers are scanned:

    1. **Built-in** — bundled with the package at
       :func:`builtin_project_workflows_dir`. Included unless
       ``include_builtins=False``.
    2. **User** — ``~/.config/darkfactory/operations/`` (personal
       workflows shared across projects). Included unless
       ``include_user=False``.
    3. **Project** — ``workflows_dir`` (typically
       ``<project>/.darkfactory/operations/``). Optional.

    Name collisions across any layers raise ``ValueError``.
    Missing layers are silently skipped (not an error).
    """
    workflows: dict[str, Workflow] = {}

    if include_builtins:
        _scan_project_workflows_layer(builtin_project_workflows_dir(), workflows)

    if include_user:
        from .config._paths import user_operations_dir

        user_dir = user_operations_dir()
        _scan_project_workflows_layer(user_dir, workflows)

    if workflows_dir is not None:
        _scan_project_workflows_layer(workflows_dir, workflows)

    return workflows


# ---------- backward-compatibility aliases ----------

# These names are used by callers that haven't been updated yet.
builtin_operations_dir = builtin_project_workflows_dir
load_operations = load_project_workflows


def _load_workflow_module(
    workflow_file: Path,
    subdir: Path,
    *,
    module_prefix: str = "_darkfactory_workflow_",
) -> Workflow:
    """Import a single workflow.py and return the Workflow instance it exports.

    Uses a synthetic module name derived from the subdirectory so two
    workflows with independent-but-identical module-level imports don't
    collide in ``sys.modules``.

    Raises ``ImportError`` if the file can't be compiled, ``AttributeError``
    if the module has no top-level ``workflow``, and ``TypeError`` if
    ``workflow`` is not a :class:`Workflow` instance.
    """
    module_name = f"{module_prefix}{subdir.name}"
    spec = importlib.util.spec_from_file_location(module_name, workflow_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create import spec for {workflow_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Remove the half-imported module so a retry can try again cleanly.
        sys.modules.pop(module_name, None)
        raise

    # Support both 'workflow' and 'operation' attribute names for legacy compat
    attr_name = "workflow"
    if not hasattr(module, "workflow") and hasattr(module, "operation"):
        attr_name = "operation"

    if not hasattr(module, attr_name):
        raise AttributeError(
            f"{workflow_file}: module does not export a 'workflow' attribute"
        )

    wf = getattr(module, attr_name)
    if not isinstance(wf, Workflow):
        raise TypeError(
            f"{workflow_file}: '{attr_name}' is not a Workflow instance "
            f"(got {type(wf).__name__})"
        )

    wf.workflow_dir = subdir
    return wf
