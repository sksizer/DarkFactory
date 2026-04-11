"""Claude Code subprocess helpers for DarkFactory.

Public API:

Interactive session (from _interactive):
- :func:`spawn_claude` — spawn an interactive Claude Code session

Invocation (from _invoke):
- :func:`invoke_claude` — run Claude Code as subprocess, parse sentinels
- :class:`InvokeResult` — structured outcome of an invocation
- :func:`capability_to_model` — map PRD capability tier to model name
"""

from ._interactive import spawn_claude
from ._invoke import InvokeResult, capability_to_model, invoke_claude

__all__ = [
    "InvokeResult",
    "capability_to_model",
    "invoke_claude",
    "spawn_claude",
]
