"""GitHub CLI (gh) utilities — typed wrappers around gh subprocess calls.

Re-exports public symbols needed by application code outside this package.
"""

from __future__ import annotations

from darkfactory.utils.github._types import (
    GhCheckResult as GhCheckResult,
    GhErr as GhErr,
    GhResult as GhResult,
)
from darkfactory.utils.github.pr import (
    close_pr as close_pr,
    list_open_prs as list_open_prs,
)
