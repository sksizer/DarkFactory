"""Model package — public API for PRD data types and persistence."""

from __future__ import annotations

from darkfactory.model._persistence import (
    CANONICAL_FIELD_ORDER as CANONICAL_FIELD_ORDER,
    TERMINAL_STATUSES as TERMINAL_STATUSES,
    archive as archive,
    dump_frontmatter as dump_frontmatter,
    ensure_data_layout as ensure_data_layout,
    load_all as load_all,
    load_one as load_one,
    normalize_list_field_at as normalize_list_field_at,
    parse_prd as parse_prd,
    save as save,
    set_status as set_status,
    set_status_at as set_status_at,
    set_workflow as set_workflow,
    update_frontmatter_field_at as update_frontmatter_field_at,
)
from darkfactory.model._prd import (
    CANONICAL_SORTS as CANONICAL_SORTS,
    FRONTMATTER_RE as FRONTMATTER_RE,
    PRD as PRD,
    PRD_ID_RE as PRD_ID_RE,
    WIKILINK_BODY_RE as WIKILINK_BODY_RE,
    WIKILINK_RE as WIKILINK_RE,
    _WIKILINK_FIELDS as _WIKILINK_FIELDS,
    _yaml_item_repr as _yaml_item_repr,
    compute_branch_name as compute_branch_name,
    parse_id_sort_key as parse_id_sort_key,
    parse_wikilink as parse_wikilink,
    parse_wikilinks as parse_wikilinks,
)
