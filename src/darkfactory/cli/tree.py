"""Tree command — display PRD containment hierarchy."""

from __future__ import annotations

import argparse
from collections.abc import Mapping

from darkfactory import containment
from darkfactory.cli._shared import _load
from darkfactory.prd import PRD
from darkfactory.style import Element, Styler


def _format_tree_node(prd: PRD, styler: Styler) -> str:
    """Return a styled inline descriptor for a tree node: ``id  [kind/status/priority]  title``."""
    kind_elem = styler.kind_element(prd.kind)
    kind_icon = styler.icon(prd.kind)
    status_icon = styler.icon(prd.status)
    priority_icon = styler.icon(prd.priority)

    styled_id = styler.render(kind_elem, prd.id)
    styled_kind = styler.render(kind_elem, f"{kind_icon}{prd.kind}")
    styled_status = styler.render(Element.TREE_STATUS, f"{status_icon}{prd.status}")
    styled_priority = styler.render(
        Element.TREE_PRIORITY, f"{priority_icon}{prd.priority}"
    )
    return (
        f"{styled_id}  [{styled_kind}/{styled_status}/{styled_priority}]  {prd.title}"
    )


def _print_tree(
    prd: PRD,
    prds: Mapping[str, PRD],
    styler: Styler,
    prefix: str = "",
    is_last: bool = True,
) -> None:
    """Recursively print a containment tree branch."""
    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{_format_tree_node(prd, styler)}")
    extension = "    " if is_last else "│   "
    kids = containment.children(prd.id, prds)
    for i, kid in enumerate(kids):
        _print_tree(kid, prds, styler, prefix + extension, i == len(kids) - 1)


def cmd_tree(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    styler: Styler = args.styler
    if args.prd_id:
        prd = prds.get(args.prd_id)
        if prd is None:
            raise SystemExit(f"unknown PRD id: {args.prd_id}")
        print(_format_tree_node(prd, styler))
        kids = containment.children(prd.id, prds)
        for i, kid in enumerate(kids):
            _print_tree(kid, prds, styler, "", i == len(kids) - 1)
    else:
        for root in containment.roots(prds):
            print(_format_tree_node(root, styler))
            kids = containment.children(root.id, prds)
            for i, kid in enumerate(kids):
                _print_tree(kid, prds, styler, "", i == len(kids) - 1)
            print()
    return 0
