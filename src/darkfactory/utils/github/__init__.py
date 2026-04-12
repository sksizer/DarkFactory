"""GitHub CLI (gh) utilities — typed wrappers around gh subprocess calls.

Re-exports all public symbols from submodules.
"""

from __future__ import annotations

from darkfactory.utils.github._cli import (
    gh_json as gh_json,
    gh_run as gh_run,
)
from darkfactory.utils.github._types import (
    GhCheckResult as GhCheckResult,
    GhErr as GhErr,
    GhResult as GhResult,
)
from darkfactory.utils.github.pr import (
    PrInfo as PrInfo,
    close_pr as close_pr,
    create_pr as create_pr,
    fetch_all_pr_states as fetch_all_pr_states,
    get_pr_state as get_pr_state,
    get_resume_pr_state as get_resume_pr_state,
    list_open_prs as list_open_prs,
)
from darkfactory.utils.github.pr.comments import (
    CommentFilters as CommentFilters,
    CommentReply as CommentReply,
    ReviewComment as ReviewComment,
    ReviewThread as ReviewThread,
    fetch_pr_comments as fetch_pr_comments,
    parse_agent_replies as parse_agent_replies,
    post_comment_replies as post_comment_replies,
)
