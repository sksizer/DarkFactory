"""Normalize command — canonicalize list fields in PRD files."""

from __future__ import annotations

import argparse
import sys

from darkfactory.cli._shared import _load
from darkfactory.prd import PRD, normalize_list_field_at, parse_id_sort_key

#: List fields that ``prd normalize`` canonicalizes.
_NORMALIZABLE_FIELDS: tuple[str, ...] = ("tags", "impacts", "depends_on", "blocks")


def _normalize_prd(prd: PRD, check_only: bool) -> bool:
    """Normalize all list fields of a single PRD. Returns True if changed."""
    changed = False
    for field in _NORMALIZABLE_FIELDS:
        raw = prd.raw_frontmatter.get(field)
        if raw is None:
            continue
        if not isinstance(raw, list):
            continue
        items = [str(v) for v in raw]
        try:
            if normalize_list_field_at(prd.path, field, items, write=not check_only):
                changed = True
        except ValueError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)
    return changed


def cmd_normalize(args: argparse.Namespace) -> int:
    """Canonicalize list fields in one or all PRD files.

    Sorts ``tags``, ``impacts``, ``depends_on``, and ``blocks`` into their
    canonical order (alphabetical for tags/impacts, natural PRD-ID order for
    the dependency fields) and rewrites only the affected lines on disk.

    With ``--check``, prints how many files would change and exits non-zero
    without writing anything — suitable for CI.
    """
    prds = _load(args.prd_dir)

    if args.all:
        targets = sorted(prds.values(), key=lambda p: parse_id_sort_key(p.id))
    elif args.prd_id:
        if args.prd_id not in prds:
            raise SystemExit(f"unknown PRD id: {args.prd_id}")
        targets = [prds[args.prd_id]]
    else:
        raise SystemExit("specify a PRD id or --all")

    changed_count = 0
    for prd in targets:
        if _normalize_prd(prd, check_only=args.check):
            changed_count += 1
            if not args.check:
                print(f"normalized: {prd.id}")

    if args.check:
        if changed_count:
            print(
                f"{changed_count} file(s) would be changed",
                file=sys.stderr,
            )
            return 1
        print(f"OK: all {len(targets)} file(s) already canonical")
        return 0

    if changed_count:
        print(f"Normalized {changed_count} of {len(targets)} file(s).")
    else:
        print(f"No changes — {len(targets)} file(s) already canonical.")
    return 0
