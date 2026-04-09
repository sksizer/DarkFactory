"""Dynamic workflow discovery.

The harness discovers workflows at runtime by scanning a directory for
subdirectories that contain a ``workflow.py`` module. Each matching
module is imported and expected to expose a top-level ``workflow``
attribute that is a :class:`~darkfactory.workflow.Workflow` instance.

This lets workflow authors drop a new workflow into
``tools/prd-harness/workflows/<name>/`` without editing any registry
or manifest — the loader picks it up automatically. The authored
``workflow.py`` can import from ``darkfactory.workflow`` and
``darkfactory.builtins`` just like any normal Python module.

Import errors in one workflow.py don't block the others — we log the
error and skip. Duplicate workflow *names* (two modules both exporting
``workflow = Workflow(name="foo")``) are a hard error since they'd
make the assignment logic ambiguous.
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
    """Return the directory containing first-party (system) workflows.

    These ship inside the installed ``darkfactory`` package at
    ``src/darkfactory/workflows/`` and are available to every install
    without any on-disk setup in the target project.

    The ``DARKFACTORY_BUILTINS_DIR`` environment variable overrides the
    default — used by the test suite to point at an empty directory so
    CLI fixture tests can isolate from the real bundled workflows.
    """
    override = os.environ.get("DARKFACTORY_BUILTINS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "workflows"


def load_workflows(
    workflows_dir: Path | None = None,
    *,
    include_builtins: bool = True,
) -> dict[str, Workflow]:
    """Discover workflows across the built-in and project layers.

    Two layers are scanned (user-level ``~/.config/darkfactory/workflows/``
    is planned but not yet wired up — see PRD-222.4/222.5):

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


def _load_workflow_module(workflow_file: Path, subdir: Path) -> Workflow:
    """Import a single workflow.py and return the Workflow instance it exports.

    Uses a synthetic module name derived from the subdirectory so two
    workflows with independent-but-identical module-level imports don't
    collide in ``sys.modules``.

    Raises ``ImportError`` if the file can't be compiled, ``AttributeError``
    if the module has no top-level ``workflow``, and ``TypeError`` if
    ``workflow`` is not a :class:`Workflow` instance.
    """
    module_name = f"_darkfactory_workflow_{subdir.name}"
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

    if not hasattr(module, "workflow"):
        raise AttributeError(
            f"{workflow_file}: module does not export a 'workflow' attribute"
        )

    wf = module.workflow
    if not isinstance(wf, Workflow):
        raise TypeError(
            f"{workflow_file}: 'workflow' is not a Workflow instance "
            f"(got {type(wf).__name__})"
        )

    wf.workflow_dir = subdir
    return wf
