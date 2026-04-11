"""GitHub CLI subprocess helpers for DarkFactory.

Public API:

Low-level CLI wrappers (from _cli):
- :func:`gh_repo_nwo` — return (owner, name) for current repo
- :func:`gh_graphql` — run gh api graphql, return parsed JSON
- :func:`gh_api` — generic gh api call

Pull request helpers (from pull_request):
- :func:`get_pr_state` — return MERGED/CLOSED/OPEN/UNKNOWN for a branch
- :func:`fetch_all_pr_states` — bulk fetch all PR states in one call
- :func:`list_prs_for_branch` — list PR dicts for a branch
- :func:`create_pull_request` — run gh pr create

Comment helpers (from comments):
- :func:`post_comment_reply` — post reply to inline review comment
"""

from ._cli import gh_api, gh_graphql, gh_repo_nwo
from .comments import post_comment_reply
from .pull_request import (
    create_pull_request,
    fetch_all_pr_states,
    get_pr_state,
    list_prs_for_branch,
)

__all__ = [
    "create_pull_request",
    "fetch_all_pr_states",
    "get_pr_state",
    "gh_api",
    "gh_graphql",
    "gh_repo_nwo",
    "list_prs_for_branch",
    "post_comment_reply",
]
