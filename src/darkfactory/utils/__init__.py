"""Orthogonal utility modules for DarkFactory.

This package contains standalone, cross-cutting concerns that are not
specific to any single domain module (PRDs, workflows, builtins, CLI).

Re-exports shared result types used across git and github subpackages.
"""

from darkfactory.utils._result import Ok as Ok
from darkfactory.utils._result import Timeout as Timeout
