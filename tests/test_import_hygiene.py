"""Enforce that private (_-prefixed) modules are only imported within their own package.

Cross-package imports of private modules are a code smell — they bypass the
public API and create tight coupling between packages. Every package should
re-export the symbols it intends to be public via its ``__init__.py``.

This test walks the AST of every ``.py`` file under ``src/darkfactory/`` and
flags any ``from darkfactory.X._Y import ...`` where X is not the file's own
package.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "darkfactory"


def _find_violations() -> list[str]:
    violations: list[str] = []

    for py in sorted(_SRC_ROOT.rglob("*.py")):
        if ".worktrees" in py.parts:
            continue

        rel = py.relative_to(_SRC_ROOT)
        # Determine which top-level package the file belongs to.
        # e.g. cli/rework.py → "cli", utils/github/pr/comments.py → "utils"
        # Root-level files (runner.py, checks.py) have file_pkg = None.
        file_pkg = rel.parts[0] if len(rel.parts) > 1 else None

        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            mod = node.module or ""
            if not mod.startswith("darkfactory."):
                continue

            segments = mod[len("darkfactory.") :].split(".")
            for i, seg in enumerate(segments):
                if seg.startswith("_"):
                    # The imported package is the first segment.
                    imported_pkg = segments[0]
                    if imported_pkg != file_pkg:
                        violations.append(
                            f"{rel}:{node.lineno}: "
                            f"cross-package private import: {mod}"
                        )
                    break

    return violations


def test_no_cross_package_private_imports() -> None:
    violations = _find_violations()
    assert violations == [], (
        "Cross-package private module imports found. "
        "Import from the package's public __init__.py instead:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
