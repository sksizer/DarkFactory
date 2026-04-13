"""Enforce that all subprocess calls live in ``utils/``.

Every ``subprocess.run`` / ``subprocess.Popen`` / ``subprocess.check_output``
call must live under ``src/darkfactory/utils/``.  Code outside ``utils/``
must delegate to a gateway function instead of calling subprocess directly.

Gateways:
- ``utils/git/_run.py``          — ``git_run()``
- ``utils/github/_cli.py``       — ``gh_run()`` / ``gh_json()``
- ``utils/shell.py``             — ``run_shell()`` / ``run_foreground()``
- ``utils/claude_code/_*.py``    — ``spawn_claude()`` / ``claude_print()`` / ``invoke_claude()``

This test AST-scans every non-test ``.py`` file under ``src/darkfactory/``
and fails if any file outside ``utils/`` makes a direct subprocess call.
No allowlist — every violation must be fixed.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "python" / "darkfactory"
_UTILS_PREFIX = "utils" + "/"  # files under utils/ are allowed

_SUBPROCESS_ATTRS = {"run", "Popen", "check_output"}


def _is_subprocess_call(node: ast.Call) -> bool:
    """Check if ``node`` is ``subprocess.run|Popen|check_output(...)``."""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _SUBPROCESS_ATTRS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _scan_violations() -> list[str]:
    """Return ``file:line`` strings for every violating call site."""
    violations: list[str] = []
    for py in sorted(_SRC_ROOT.rglob("*.py")):
        if ".worktrees" in py.parts:
            continue
        rel = str(py.relative_to(_SRC_ROOT))
        # Skip test files.
        if py.name.endswith("_test.py") or py.name.startswith("test_"):
            continue
        # Files under utils/ are the designated gateway layer.
        if rel.startswith(_UTILS_PREFIX):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_subprocess_call(node):
                violations.append(f"{rel}:{node.lineno}")
    return violations


def test_no_subprocess_calls_outside_utils() -> None:
    """All subprocess calls must live under utils/."""
    violations = _scan_violations()
    assert violations == [], (
        "Direct subprocess calls found outside utils/.\n"
        "Route through the appropriate gateway in utils/ instead:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
