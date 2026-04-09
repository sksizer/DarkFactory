"""Cascade workflow registry.

Discovers workflows from all three layers (built-in, user, project),
validates each against the workflow API contract, and enforces strict
name uniqueness across layers. Any name collision is a hard error at
startup. Any workflow failing API validation is a hard error with a
clear diagnostic message naming the layer, file path, and violation.
"""

from __future__ import annotations

from pathlib import Path

from darkfactory.loader import load_workflows
from darkfactory.paths import user_workflows_dir
from darkfactory.workflow import Workflow
from darkfactory.workflows import get_builtin_workflows


class WorkflowNameCollision(Exception):
    """Raised when the same workflow name appears in multiple layers."""

    def __init__(self, name: str, locations: list[tuple[str, Path]]) -> None:
        self.name = name
        self.locations = locations
        parts = [f"{layer}:{p}" for layer, p in locations]
        super().__init__(
            f"Workflow '{name}' found in multiple layers: {parts}. "
            "Rename or delete one to resolve."
        )


class InvalidWorkflow(Exception):
    """Raised when a workflow fails API contract validation."""

    def __init__(self, layer: str, path: Path, reason: str) -> None:
        self.layer = layer
        self.path = path
        self.reason = reason
        super().__init__(
            f"Workflow at {path} (layer: {layer}) failed validation: {reason}."
        )


def _validate_workflow(wf: Workflow, layer: str, path: Path) -> None:
    """Validate a workflow against the expected API contract."""
    if not hasattr(wf, "name") or not wf.name:
        raise InvalidWorkflow(layer, path, "'name' attribute is missing or empty")
    if not hasattr(wf, "tasks") or not isinstance(wf.tasks, list):
        raise InvalidWorkflow(
            layer,
            path,
            f"'tasks' must be a list; got {type(wf.tasks).__name__}",
        )
    if not hasattr(wf, "applies_to") or not callable(wf.applies_to):
        raise InvalidWorkflow(layer, path, "'applies_to' must be callable")


def build_workflow_registry(project_dir: Path | None = None) -> dict[str, Workflow]:
    """Discover, validate, and return all workflows from all layers.

    Collects workflows from three layers in priority order:

    1. **Built-in** — bundled with the package via
       :func:`darkfactory.workflows.get_builtin_workflows`.
    2. **User** — ``~/.config/darkfactory/workflows/`` via
       :func:`~darkfactory.loader.load_workflows`.
    3. **Project** — ``<project_dir>/workflows/`` via
       :func:`~darkfactory.loader.load_workflows`.

    Name collisions across any two layers raise
    :class:`WorkflowNameCollision`. Workflows failing API contract
    validation raise :class:`InvalidWorkflow`. Both are fatal.
    """
    # registry maps name -> (layer, path, workflow)
    registry: dict[str, tuple[str, Path, Workflow]] = {}

    # Layer 1: built-in
    for name, wf in get_builtin_workflows().items():
        _validate_workflow(wf, "built-in", Path("<package>") / name)
        registry[name] = ("built-in", Path("<package>") / name, wf)

    # Layer 2: user
    user_dir = user_workflows_dir()
    if user_dir.is_dir():
        for name, wf in load_workflows(user_dir, include_builtins=False).items():
            _validate_workflow(wf, "user", user_dir / name)
            if name in registry:
                existing_layer, existing_path, _ = registry[name]
                raise WorkflowNameCollision(
                    name,
                    [
                        (existing_layer, existing_path),
                        ("user", user_dir / name),
                    ],
                )
            registry[name] = ("user", user_dir / name, wf)

    # Layer 3: project
    if project_dir is not None:
        proj_wf_dir = project_dir / "workflows"
        if proj_wf_dir.is_dir():
            for name, wf in load_workflows(proj_wf_dir, include_builtins=False).items():
                _validate_workflow(wf, "project", proj_wf_dir / name)
                if name in registry:
                    existing_layer, existing_path, _ = registry[name]
                    raise WorkflowNameCollision(
                        name,
                        [
                            (existing_layer, existing_path),
                            ("project", proj_wf_dir / name),
                        ],
                    )
                registry[name] = ("project", proj_wf_dir / name, wf)

    return {name: wf for name, (_, _, wf) in registry.items()}
