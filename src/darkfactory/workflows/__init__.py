"""Built-in workflows shipped with the darkfactory package.

These workflows live under ``src/darkfactory/workflows/`` and are
installed as part of the wheel. Use :func:`get_builtin_workflows` to
load all three at runtime without filesystem scanning.
"""

from __future__ import annotations

from pathlib import Path

from darkfactory.loader import _load_workflow_module
from darkfactory.workflow import Workflow

BUILTIN_WORKFLOW_NAMES = ["default", "extraction", "planning"]


def get_builtin_workflows() -> dict[str, Workflow]:
    """Load all built-in workflows shipped with the package."""
    result = {}
    base = Path(__file__).parent
    for name in BUILTIN_WORKFLOW_NAMES:
        subdir = base / name
        wf_file = subdir / "workflow.py"
        if wf_file.exists():
            wf = _load_workflow_module(wf_file, subdir)
            result[name] = wf
    return result
