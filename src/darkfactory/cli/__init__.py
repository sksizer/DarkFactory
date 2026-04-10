"""CLI package.

Re-exports ``main`` and ``build_parser`` as the public API.
"""

from __future__ import annotations

from darkfactory.cli._parser import build_parser
from darkfactory.cli.main import main

__all__ = ["main", "build_parser"]
