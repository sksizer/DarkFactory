"""Enforce that git/gh subprocess calls go through the gateway layer.

All ``subprocess.run`` / ``subprocess.Popen`` / ``subprocess.check_output``
calls invoking ``git`` or ``gh`` must use the designated gateways:

- ``utils/git/_run.py``  — ``git_run()``
- ``utils/github/_cli.py`` — ``gh_run()`` / ``gh_json()``

This test AST-scans every ``.py`` file under ``src/darkfactory/`` and fails
if any non-allowlisted file makes a direct git/gh subprocess call.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "darkfactory"

# Primary gateways — these ARE the subprocess entry points.
_GATEWAY_FILES = {
    "utils/git/_run.py",
    "utils/github/_cli.py",
}

# Files allowed to bypass the gateways with justification.
# Every entry MUST still contain the violation — if it's cleaned up,
# the staleness test below forces removal from this dict.
_BYPASS_ALLOWLIST: dict[str, str] = {
    "utils/git/_operations.py": "diff_show: terminal passthrough (no capture_output)",
    "workflow/definitions/project/verify_merges/check.py": "standalone __main__ script",
}

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


def _first_arg_is_git_or_gh(node: ast.Call) -> bool:
    """Heuristic: does the first positional arg start with ``git`` or ``gh``?

    Handles string literals (``subprocess.run("git ...")``) and list/tuple
    literals (``subprocess.run(["git", "..."])``).  Variable arguments are
    conservatively treated as non-git/gh — the import-hygiene test and code
    review catch those.
    """
    if not node.args:
        return False
    first = node.args[0]
    # Direct string: subprocess.run("git ...")
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value.startswith(("git", "gh"))
    # List/tuple literal: subprocess.run(["git", ...])
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        elt = first.elts[0]
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            return elt.value in ("git", "gh")
    # BinOp: subprocess.run(["git", ...] + other_list)
    if isinstance(first, ast.BinOp) and isinstance(first.left, (ast.List, ast.Tuple)):
        if first.left.elts:
            elt = first.left.elts[0]
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                return elt.value in ("git", "gh")
    return False


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
        # Skip gateways and explicitly allowed files.
        if rel in _GATEWAY_FILES or rel in _BYPASS_ALLOWLIST:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _is_subprocess_call(node)
                and _first_arg_is_git_or_gh(node)
            ):
                violations.append(f"{rel}:{node.lineno}")
    return violations


def _scan_stale_allowlist() -> list[str]:
    """Return entries in ``_BYPASS_ALLOWLIST`` whose file no longer violates."""
    stale: list[str] = []
    for rel in sorted(_BYPASS_ALLOWLIST):
        py = _SRC_ROOT / rel
        if not py.exists():
            stale.append(f"{rel}: file does not exist")
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            stale.append(f"{rel}: SyntaxError")
            continue
        # Check for ANY subprocess call (not just literal git/gh) because
        # some bypass patterns use variable args (e.g. _run(cmd)) or
        # list concatenation (["git", ...] + paths).
        has_violation = any(
            isinstance(node, ast.Call) and _is_subprocess_call(node)
            for node in ast.walk(tree)
        )
        if not has_violation:
            stale.append(f"{rel}: no git/gh subprocess calls found — remove from allowlist")
    return stale


def test_no_direct_git_gh_subprocess_calls() -> None:
    """All git/gh subprocess calls must go through the gateway layer."""
    violations = _scan_violations()
    assert violations == [], (
        "Direct git/gh subprocess calls found outside the gateway layer.\n"
        "Use git_run() from utils/git/ or gh_run()/gh_json() from utils/github/ instead:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_bypass_allowlist_is_not_stale() -> None:
    """Every bypass-allowlisted file must still contain a violation.

    If you've migrated a file to use the gateways, remove it from the
    ``_BYPASS_ALLOWLIST`` dict so the allowlist only shrinks over time.
    """
    stale = _scan_stale_allowlist()
    assert stale == [], (
        "Stale entries in _BYPASS_ALLOWLIST — these files no longer bypass "
        "the gateway and should be removed:\n"
        + "\n".join(f"  {s}" for s in stale)
    )
