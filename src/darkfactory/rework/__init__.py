"""Rework subsystem — context discovery, loop guard, and prompt rendering."""

from darkfactory.rework.context import (
    ReworkContext as ReworkContext,
    ReworkError as ReworkError,
    discover_rework_context as discover_rework_context,
    find_open_pr as find_open_pr,
)
from darkfactory.rework.guard import (
    DEFAULT_MAX_CONSECUTIVE as DEFAULT_MAX_CONSECUTIVE,
    GuardOutcome as GuardOutcome,
    ReworkGuard as ReworkGuard,
)
from darkfactory.rework.prompt import (
    render_rework_feedback as render_rework_feedback,
)
