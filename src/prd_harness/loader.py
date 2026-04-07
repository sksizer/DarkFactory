"""Dynamic workflow discovery.

The harness discovers workflows at runtime by scanning a directory for
subdirectories that contain a ``workflow.py`` module. Each matching
module is imported and expected to expose a top-level ``workflow``
attribute that is a :class:`~prd_harness.workflow.Workflow` instance.

This lets workflow authors drop a new workflow into
``tools/prd-harness/workflows/<name>/`` without editing any registry
or manifest — the loader picks it up automatically. The authored
``workflow.py`` can import from ``prd_harness.workflow`` and
``prd_harness.builtins`` just like any normal Python module.

Import errors in one workflow.py don't block the others — we log the
error and skip. Duplicate workflow *names* (two modules both exporting
``workflow = Workflow(name="foo")``) are a hard error since they'd
make the assignment logic ambiguous.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from .workflow import Workflow

logger = logging.getLogger("prd_harness.loader")


def load_workflows(workflows_dir: Path) -> dict[str, Workflow]:
    """Scan ``workflows_dir`` for workflow modules and return a name->Workflow dict.

    Each direct subdirectory is inspected for a ``workflow.py`` file. When
    found, the module is loaded via ``importlib`` with a unique synthetic
    module name (to avoid collisions with other harness workflows that
    might share a package name) and registered in ``sys.modules`` so
    relative imports inside the workflow module resolve correctly.

    After import, the module must expose a top-level ``workflow``
    attribute that is a :class:`Workflow` instance. The loader sets
    ``workflow.workflow_dir`` to the subdirectory path so
    ``AgentTask.prompts`` paths can be resolved relative to it at
    runtime.

    Returns an empty dict if ``workflows_dir`` doesn't exist — this is
    not an error; the caller can start with no workflows and add them
    later.

    Raises ``ValueError`` on duplicate workflow names. Import errors in
    individual workflow modules are logged at WARNING level and the
    module is skipped; the rest of the scan continues.
    """
    workflows: dict[str, Workflow] = {}

    if not workflows_dir.exists() or not workflows_dir.is_dir():
        logger.debug("workflows directory not found: %s", workflows_dir)
        return workflows

    for subdir in sorted(workflows_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_") or subdir.name.startswith("."):
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
    module_name = f"_prd_harness_workflow_{subdir.name}"
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
