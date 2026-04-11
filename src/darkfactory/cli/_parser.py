"""Argument parser for the CLI package."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    # Extracted submodules — import directly
    from darkfactory.cli.archive import cmd_archive
    from darkfactory.cli.assign_cmd import cmd_assign
    from darkfactory.cli.children import cmd_children
    from darkfactory.cli.cleanup import cmd_cleanup
    from darkfactory.cli.conflicts import cmd_conflicts
    from darkfactory.cli.list_workflows import cmd_list_workflows
    from darkfactory.cli.new import cmd_new
    from darkfactory.cli.next_cmd import cmd_next
    from darkfactory.cli.normalize import cmd_normalize
    from darkfactory.cli.orphans import cmd_orphans
    from darkfactory.cli.plan import cmd_plan
    from darkfactory.cli.reconcile import cmd_reconcile
    from darkfactory.cli.run import cmd_run
    from darkfactory.cli.status import cmd_status
    from darkfactory.cli.tree import cmd_tree
    from darkfactory.cli.undecomposed import cmd_undecomposed
    from darkfactory.cli.validate import cmd_validate

    from darkfactory.cli.discuss import cmd_discuss
    from darkfactory.cli.init_cmd import cmd_init
    from darkfactory.cli.rework import cmd_rework
    from darkfactory.cli.rework_watch import cmd_rework_watch
    from darkfactory.cli.system import (
        cmd_system_describe,
        cmd_system_list,
        cmd_system_run,
    )

    parser = argparse.ArgumentParser(prog="prd", description="Pumice PRD harness CLI")
    parser.add_argument(
        "--directory",
        "-C",
        type=Path,
        default=None,
        metavar="DIR",
        help="Project root containing .darkfactory/ (overrides DARKFACTORY_DIR env and walk-up)",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=None,
        help="Path to workflows directory (default: tools/prd-harness/workflows)",
    )
    parser.add_argument(
        "--operations-dir",
        type=Path,
        default=None,
        dest="operations_dir",
        help="Path to system operations directory (default: .darkfactory/operations/)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON output where supported"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--theme",
        default=None,
        choices=["dark", "light"],
        help="Color theme (default: dark)",
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        default=False,
        help="Disable all color output",
    )
    parser.add_argument(
        "--icon-set",
        dest="icon_set",
        default=None,
        choices=["nerdfont", "ascii", "emoji"],
        help="Icon set to use (default: auto-detected, ascii fallback)",
    )

    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub_init = sub.add_parser(
        "init", help="Scaffold .darkfactory/ in the current project"
    )
    sub_init.set_defaults(func=cmd_init)

    sub_archive = sub.add_parser(
        "archive", help="Move a completed PRD to the archive"
    )
    sub_archive.add_argument("prd_id", help="PRD id to archive (e.g. PRD-070)")
    sub_archive.set_defaults(func=cmd_archive)

    sub_new = sub.add_parser("new", help="Create a new draft PRD from a template")
    sub_new.add_argument("title", help="PRD title (positional)")
    sub_new.add_argument(
        "--id", default=None, help="Explicit PRD id (default: next flat id)"
    )
    sub_new.add_argument(
        "--kind", default="task", choices=["epic", "feature", "component", "task"]
    )
    sub_new.add_argument(
        "--priority", default="medium", choices=["critical", "high", "medium", "low"]
    )
    sub_new.add_argument("--effort", default="m", choices=["xs", "s", "m", "l", "xl"])
    sub_new.add_argument(
        "--capability",
        default="moderate",
        choices=["trivial", "simple", "moderate", "complex"],
    )
    sub_new.add_argument(
        "--open",
        action="store_true",
        help="Open the new file in $EDITOR after creation",
    )
    sub_new.add_argument(
        "--discuss",
        action="store_true",
        help=(
            "Launch an interactive Claude Code discussion session for the new PRD. "
            "Composes with --open: editor opens first, then the discuss chain starts."
        ),
    )
    sub_new.set_defaults(func=cmd_new)

    _discuss_help = (
        "Open an interactive Claude Code discussion for a PRD. "
        "Runs a chain of phases: gather context, collaborative discussion, "
        "critical review, and an optional commit of PRD edits. "
        "Each phase launches Claude Code interactively; exit with /exit or "
        "Ctrl-D to advance to the next phase."
    )
    sub_discuss = sub.add_parser(
        "discuss",
        help=_discuss_help,
        description=_discuss_help,
    )
    sub_discuss.add_argument("prd_id", help="PRD id to discuss (e.g. PRD-070)")
    sub_discuss.set_defaults(func=cmd_discuss)

    sub_status = sub.add_parser("status", help="DAG overview and counts")
    sub_status.set_defaults(func=cmd_status)

    sub_cleanup = sub.add_parser("cleanup", help="Remove worktrees for completed PRDs")
    sub_cleanup.add_argument(
        "prd_id",
        nargs="?",
        default=None,
        help="PRD id to clean up (e.g. PRD-224.4)",
    )
    sub_cleanup.add_argument(
        "--merged",
        action="store_true",
        help="Remove all worktrees for merged-PR PRDs",
    )
    sub_cleanup.add_argument(
        "--all",
        dest="all_",
        action="store_true",
        help="Remove all worktrees (with confirmation prompt)",
    )
    sub_cleanup.add_argument(
        "--force",
        action="store_true",
        help="Remove even if there are unpushed commits",
    )
    sub_cleanup.set_defaults(func=cmd_cleanup)

    sub_next = sub.add_parser("next", help="List actionable PRDs")
    sub_next.add_argument("--limit", type=int, default=10)
    sub_next.add_argument(
        "--capability", default="", help="Comma-separated capability filter"
    )
    sub_next.set_defaults(func=cmd_next)

    sub_validate = sub.add_parser("validate", help="Cycle/missing-dep/orphan checks")
    sub_validate.set_defaults(func=cmd_validate)

    sub_tree = sub.add_parser("tree", help="Show containment tree")
    sub_tree.add_argument(
        "prd_id", nargs="?", help="Root PRD id (default: full forest)"
    )
    sub_tree.set_defaults(func=cmd_tree)

    sub_children = sub.add_parser("children", help="Direct children of a PRD")
    sub_children.add_argument("prd_id")
    sub_children.set_defaults(func=cmd_children)

    sub_orphans = sub.add_parser("orphans", help="Top-level PRDs (no parent)")
    sub_orphans.set_defaults(func=cmd_orphans)

    sub_undec = sub.add_parser(
        "undecomposed", help="Epics/features lacking task children"
    )
    sub_undec.set_defaults(func=cmd_undecomposed)

    sub_conflicts = sub.add_parser("conflicts", help="Show file impact overlaps")
    sub_conflicts.add_argument("prd_id")
    sub_conflicts.set_defaults(func=cmd_conflicts)

    sub_list_wfs = sub.add_parser(
        "list-workflows", help="Show loaded workflows with priorities"
    )
    sub_list_wfs.set_defaults(func=cmd_list_workflows)

    sub_assign = sub.add_parser(
        "assign",
        help="Compute workflow assignment per PRD (optionally persist)",
    )
    sub_assign.add_argument(
        "--write",
        action="store_true",
        help="Persist assignments to PRD frontmatter (only for unassigned PRDs)",
    )
    sub_assign.set_defaults(func=cmd_assign)

    sub_normalize = sub.add_parser(
        "normalize",
        help="Canonicalize list fields (tags, impacts, depends_on, blocks)",
    )
    sub_normalize.add_argument(
        "prd_id",
        nargs="?",
        help="PRD id to normalize (e.g. PRD-070); required unless --all",
    )
    sub_normalize.add_argument(
        "--all",
        action="store_true",
        help="Normalize every PRD in the directory",
    )
    sub_normalize.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any file would change without writing",
    )
    sub_normalize.set_defaults(func=cmd_normalize)

    sub_plan = sub.add_parser(
        "plan",
        help="Show the execution plan for a PRD without touching anything",
    )
    sub_plan.add_argument("prd_id")
    sub_plan.add_argument(
        "--workflow",
        default=None,
        help="Override the workflow assignment (by name)",
    )
    sub_plan.add_argument(
        "--base",
        default=None,
        help="Base ref for the new branch (default: current HEAD)",
    )
    sub_plan.add_argument(
        "--model",
        default=None,
        help="Override the capability->model mapping (e.g. opus)",
    )
    sub_plan.set_defaults(func=cmd_plan)

    sub_run = sub.add_parser(
        "run",
        help="Run a workflow against a PRD (dry-run unless --execute)",
    )
    sub_run.add_argument("prd_id", nargs="?", default=None)
    sub_run.add_argument(
        "--all",
        dest="run_all",
        action="store_true",
        help="Drain the ready queue: run all ready PRDs without a target",
    )
    sub_run.add_argument(
        "--priority",
        default=None,
        choices=["critical", "high", "medium", "low"],
        help="Only run PRDs at or above this priority",
    )
    sub_run.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=None,
        help="Only run PRDs with this tag (repeatable, OR semantics)",
    )
    sub_run.add_argument(
        "--exclude",
        dest="exclude_ids",
        action="append",
        default=None,
        help="Exclude specific PRD IDs (repeatable)",
    )
    sub_run.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute (default is dry-run)",
    )
    sub_run.add_argument(
        "--workflow",
        default=None,
        help="Override the workflow assignment (by name)",
    )
    sub_run.add_argument(
        "--base",
        default=None,
        help="Base ref for the new branch (default: current HEAD)",
    )
    sub_run.add_argument(
        "--model",
        default=None,
        help="Override the capability->model mapping (e.g. opus)",
    )
    sub_run.add_argument(
        "--max-runs",
        type=int,
        default=None,
        dest="max_runs",
        help=(
            "In graph mode, cap the total number of PRD runs this "
            "invocation may execute (counts successes, failures, and "
            "mid-run introduced PRDs). Default: unbounded."
        ),
    )
    sub_run.add_argument(
        "--timeout",
        type=int,
        default=None,
        dest="timeout",
        help="Override timeout in minutes (overrides all other timeout sources)",
    )
    sub_run.set_defaults(func=cmd_run)

    p_rework = sub.add_parser("rework", help="Address PR review feedback for a PRD")
    p_rework.add_argument("prd_id", help="PRD ID to rework")
    p_rework.add_argument("--execute", action="store_true")
    p_rework.add_argument("--all", action="store_true", help="Include resolved threads")
    p_rework.add_argument("--since", help="Only comments after this commit")
    p_rework.add_argument("--reviewer", help="Only comments from this reviewer")
    p_rework.add_argument("--from-pr-comment", help="Address a single comment by ID")
    p_rework.add_argument(
        "--reply-to-comments",
        action="store_true",
        help="Post replies on addressed comments",
    )
    p_rework.set_defaults(func=cmd_rework)

    p_rework_watch = sub.add_parser(
        "rework-watch",
        help="Polling daemon: auto-trigger rework when new PR comments appear",
    )
    _rw_mode = p_rework_watch.add_mutually_exclusive_group()
    _rw_mode.add_argument(
        "--daemon",
        action="store_true",
        help="Fork and run in background (writes PID file)",
    )
    _rw_mode.add_argument(
        "--status",
        action="store_true",
        help="Print daemon status and exit",
    )
    _rw_mode.add_argument(
        "--pause",
        action="store_true",
        help="Create pause file (halts polling without stopping)",
    )
    _rw_mode.add_argument(
        "--resume",
        action="store_true",
        help="Remove pause file (resume polling)",
    )
    _rw_mode.add_argument(
        "--stop",
        action="store_true",
        help="Send SIGTERM to daemon and exit",
    )
    p_rework_watch.add_argument(
        "--interval",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Poll interval in seconds (default: 60)",
    )
    p_rework_watch.add_argument(
        "--max-reworks",
        type=int,
        default=3,
        dest="max_reworks",
        metavar="N",
        help="Max rework cycles per PR per hour (default: 3)",
    )
    p_rework_watch.set_defaults(func=cmd_rework_watch)

    sub_reconcile = sub.add_parser(
        "reconcile",
        help="Find merged-but-not-flipped PRDs and reconcile their status",
    )
    sub_reconcile.add_argument(
        "--execute",
        action="store_true",
        help="Apply the status updates (default is dry-run)",
    )
    sub_reconcile.add_argument(
        "--commit-to-main",
        dest="commit_to_main",
        action="store_true",
        default=False,
        help="Commit directly to main instead of opening a PR",
    )
    sub_reconcile.set_defaults(func=cmd_reconcile)

    # ---------- system subcommand ----------

    sub_system = sub.add_parser(
        "system",
        help="Discover and run system operations",
    )
    system_sub = sub_system.add_subparsers(
        dest="system_subcommand", metavar="SUBCOMMAND", required=True
    )

    # system list
    sub_sys_list = system_sub.add_parser(
        "list", help="List all available system operations"
    )
    sub_sys_list.set_defaults(func=cmd_system_list)

    # system describe <name>
    sub_sys_describe = system_sub.add_parser(
        "describe", help="Show metadata and task list for a system operation"
    )
    sub_sys_describe.add_argument("name", help="Operation name")
    sub_sys_describe.set_defaults(func=cmd_system_describe)

    # system run <name>
    sub_sys_run = system_sub.add_parser(
        "run",
        help="Run a system operation (dry-run unless --execute)",
    )
    sub_sys_run.add_argument("name", help="Operation name")
    sub_sys_run.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute (default is dry-run)",
    )
    sub_sys_run.add_argument(
        "--target",
        default=None,
        metavar="PRD-X",
        help="Target PRD id for operations that accept_target=True",
    )
    sub_sys_run.add_argument(
        "--model",
        default=None,
        help="Override the model for agent tasks (e.g. opus)",
    )
    sub_sys_run.set_defaults(func=cmd_system_run)

    return parser
