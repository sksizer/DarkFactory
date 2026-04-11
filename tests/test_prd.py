"""Tests for the PRD parser, sort key, and frontmatter round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.model import (
    update_frontmatter_field_at,
    PRD_ID_RE,
    load_all,
    normalize_list_field_at,
    parse_id_sort_key,
    parse_prd,
    parse_wikilink,
    parse_wikilinks,
    set_status,
)

from .conftest import write_prd


# ---------- ID matching ----------


def test_prd_id_re_matches_flat() -> None:
    assert PRD_ID_RE.match("PRD-001")
    assert PRD_ID_RE.match("PRD-070")
    assert PRD_ID_RE.match("PRD-110")


def test_prd_id_re_matches_hierarchical() -> None:
    assert PRD_ID_RE.match("PRD-1")
    assert PRD_ID_RE.match("PRD-1.2")
    assert PRD_ID_RE.match("PRD-4.2.1.3")


def test_prd_id_re_rejects_garbage() -> None:
    assert not PRD_ID_RE.match("PRD")
    assert not PRD_ID_RE.match("PRD-")
    assert not PRD_ID_RE.match("PRD-1.2.")
    assert not PRD_ID_RE.match("RFC-1")


# ---------- natural sort key ----------


def test_sort_key_flat() -> None:
    assert parse_id_sort_key("PRD-070") == (70,)
    assert parse_id_sort_key("PRD-001") == (1,)


def test_sort_key_hierarchical() -> None:
    assert parse_id_sort_key("PRD-4.2.1.3") == (4, 2, 1, 3)


def test_sort_key_orders_naturally() -> None:
    ids = ["PRD-1.10", "PRD-1.2", "PRD-1.1", "PRD-1.20"]
    assert sorted(ids, key=parse_id_sort_key) == [
        "PRD-1.1",
        "PRD-1.2",
        "PRD-1.10",
        "PRD-1.20",
    ]


# ---------- wikilink parsing ----------


def test_parse_wikilink_flat() -> None:
    assert parse_wikilink("[[PRD-070-tera-filter-obsidian-link]]") == "PRD-070"


def test_parse_wikilink_hierarchical() -> None:
    assert parse_wikilink("[[PRD-4.1.1-tera-filter]]") == "PRD-4.1.1"


def test_parse_wikilink_returns_none_for_garbage() -> None:
    assert parse_wikilink(None) is None
    assert parse_wikilink("") is None
    assert parse_wikilink("not a wikilink") is None
    assert parse_wikilink("[[Foo]]") is None


def test_parse_wikilinks_skips_invalid() -> None:
    inputs = ["[[PRD-070-foo]]", "garbage", "[[PRD-1.2-bar]]"]
    assert parse_wikilinks(inputs) == ["PRD-070", "PRD-1.2"]


def test_parse_wikilinks_handles_none() -> None:
    assert parse_wikilinks(None) == []
    assert parse_wikilinks([]) == []


# ---------- file parsing ----------


def test_parse_prd_minimal(tmp_prd_dir: Path) -> None:
    path = write_prd(tmp_prd_dir / "prds", "PRD-070", "minimal-task")
    prd = parse_prd(path)
    assert prd.id == "PRD-070"
    assert prd.slug == "minimal-task"
    assert prd.title == "Test PRD"
    assert prd.kind == "task"
    assert prd.status == "ready"
    assert prd.parent is None
    assert prd.depends_on == []
    assert prd.impacts == []
    assert prd.workflow is None


def test_parse_prd_with_relations(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir / "prds", "PRD-001", "epic", kind="epic")
    path = write_prd(
        tmp_prd_dir / "prds",
        "PRD-070",
        "child",
        parent="PRD-001",
        depends_on=["PRD-069"],
        blocks=["PRD-071"],
        impacts=["src/foo.rs", "src/bar.rs"],
        workflow="ui-component",
    )
    prd = parse_prd(path)
    assert prd.parent == "PRD-001"
    assert prd.depends_on == ["PRD-069"]
    assert prd.blocks == ["PRD-071"]
    assert prd.impacts == ["src/foo.rs", "src/bar.rs"]
    assert prd.workflow == "ui-component"


def test_load_all_skips_underscore_files(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir / "prds", "PRD-001", "first")
    (tmp_prd_dir / "prds" / "_template.md").write_text("---\nid: bogus\n---\n", encoding="utf-8")
    prds = load_all(tmp_prd_dir)
    assert set(prds.keys()) == {"PRD-001"}


def test_load_all_rejects_duplicate_ids(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir / "prds", "PRD-001", "a")
    write_prd(tmp_prd_dir / "prds", "PRD-001", "b")
    with pytest.raises(ValueError, match="duplicate"):
        load_all(tmp_prd_dir)


# ---------- frontmatter round-trip ----------


def test_set_status_preserves_body(tmp_prd_dir: Path) -> None:
    path = write_prd(tmp_prd_dir / "prds", "PRD-070", "task", body="# Title\n\nLine 1\nLine 2\n")
    prd = parse_prd(path)
    set_status(prd, "in-progress")
    reread = parse_prd(path)
    assert reread.status == "in-progress"
    assert "Line 1" in reread.body
    assert "Line 2" in reread.body


def test_set_status_bumps_updated(tmp_prd_dir: Path) -> None:
    from datetime import date

    path = write_prd(tmp_prd_dir / "prds", "PRD-070", "task")
    prd = parse_prd(path)
    set_status(prd, "review")
    reread = parse_prd(path)
    # The on-disk value is single-quoted ('2026-04-07') so PyYAML
    # round-trips it as a string instead of auto-coercing to date.
    assert reread.raw_frontmatter["updated"] == date.today().isoformat()


# ---------- update_frontmatter_field_at byte-preservation ----------


def test_update_frontmatter_field_at_preserves_other_fields_byte_for_byte(
    tmp_prd_dir: Path,
) -> None:
    """Single-field updates must not touch any other byte in the file —
    not other frontmatter fields, not their quoting style, not the body.
    This is the PRD-214 invariant."""
    raw = (
        "---\n"
        'id: "PRD-070"\n'
        "title: Example\n"
        "kind: task\n"
        "status: ready\n"
        "priority: high\n"
        'parent: "[[PRD-001-foo]]"\n'
        "depends_on: []\n"
        "blocks:\n"
        '  - "[[PRD-072-bar]]"\n'
        "impacts: []\n"
        "workflow: null\n"
        "target_version: null\n"
        "created: 2026-04-01\n"
        "updated: 2026-04-01\n"
        "tags:\n"
        "  - foo\n"
        "---\n"
        "\n"
        "# Body content\n"
        "\n"
        "Some text with `backticks` and [[wikilinks]].\n"
    )
    path = tmp_prd_dir / "PRD-070-example.md"
    path.write_text(raw, encoding="utf-8")

    update_frontmatter_field_at(path, {"status": "in-progress"})

    after = path.read_text(encoding="utf-8")
    expected = raw.replace("status: ready", "status: in-progress")
    assert after == expected, "only the status line should change"


def test_update_frontmatter_field_at_multiple_fields(tmp_prd_dir: Path) -> None:
    raw = "---\nstatus: ready\nupdated: 2026-04-01\nid: PRD-070\n---\nbody\n"
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text(raw, encoding="utf-8")
    update_frontmatter_field_at(path, {"status": "review", "updated": "'2026-04-08'"})
    after = path.read_text(encoding="utf-8")
    assert "status: review\n" in after
    assert "updated: '2026-04-08'\n" in after
    assert "id: PRD-070\n" in after  # untouched
    assert after.endswith("body\n")


def test_update_frontmatter_field_at_missing_field_raises(
    tmp_prd_dir: Path,
) -> None:
    raw = "---\nstatus: ready\n---\nbody\n"
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="missing frontmatter field"):
        update_frontmatter_field_at(path, {"nonexistent": "value"})


def test_update_frontmatter_field_at_no_frontmatter_raises(
    tmp_prd_dir: Path,
) -> None:
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text("just body, no frontmatter\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no leading frontmatter"):
        update_frontmatter_field_at(path, {"status": "review"})


# ---------- normalize_list_field_at ----------


def test_normalize_list_field_at_tags_sorted_alphabetically(tmp_prd_dir: Path) -> None:
    """AC-1: tags are sorted case-insensitively."""
    raw = '---\nid: "PRD-070"\ntags:\n  - zebra\n  - Apple\n  - mango\n---\n# Body\n'
    path = tmp_prd_dir / "PRD-070-test.md"
    path.write_text(raw, encoding="utf-8")
    changed = normalize_list_field_at(path, "tags", ["zebra", "Apple", "mango"])
    assert changed
    after = path.read_text(encoding="utf-8")
    # Apple (casefold: apple) < mango < zebra
    idx_apple = after.index("  - Apple\n")
    idx_mango = after.index("  - mango\n")
    idx_zebra = after.index("  - zebra\n")
    assert idx_apple < idx_mango < idx_zebra


def test_normalize_list_field_at_tags_only_writes_that_field(
    tmp_prd_dir: Path,
) -> None:
    """AC-1: only the tags lines change; everything else is byte-identical."""
    raw = (
        "---\n"
        'id: "PRD-070"\n'
        "status: ready\n"
        "tags:\n"
        "  - zebra\n"
        "  - Apple\n"
        "  - mango\n"
        "---\n"
        "# Body content\n"
    )
    path = tmp_prd_dir / "PRD-070-test.md"
    path.write_text(raw, encoding="utf-8")
    normalize_list_field_at(path, "tags", ["zebra", "Apple", "mango"])
    after = path.read_text(encoding="utf-8")
    # Build the expected result: only the tags block changes.
    expected = raw.replace(
        "tags:\n  - zebra\n  - Apple\n  - mango\n",
        "tags:\n  - Apple\n  - mango\n  - zebra\n",
    )
    assert after == expected


def test_normalize_list_field_at_blocks_natural_sort(tmp_prd_dir: Path) -> None:
    """AC-2: blocks are sorted by natural PRD ID (PRD-1.2 before PRD-1.10)."""
    raw = (
        "---\n"
        'id: "PRD-070"\n'
        "blocks:\n"
        '  - "[[PRD-1.10-slug]]"\n'
        '  - "[[PRD-1.2-slug]]"\n'
        "tags: []\n"
        "---\n"
        "# Body\n"
    )
    path = tmp_prd_dir / "PRD-070-test.md"
    path.write_text(raw, encoding="utf-8")
    changed = normalize_list_field_at(
        path,
        "blocks",
        ["[[PRD-1.10-slug]]", "[[PRD-1.2-slug]]"],
    )
    assert changed
    after = path.read_text(encoding="utf-8")
    pos_1_2 = after.index("PRD-1.2-slug")
    pos_1_10 = after.index("PRD-1.10-slug")
    assert pos_1_2 < pos_1_10, "PRD-1.2 must sort before PRD-1.10"


def test_normalize_list_field_at_preserves_other_fields_byte_for_byte(
    tmp_prd_dir: Path,
) -> None:
    """AC-3: normalizing tags leaves every other byte unchanged."""
    raw = (
        "---\n"
        'id: "PRD-070"\n'
        "status: ready\n"
        "tags:\n"
        "  - zebra\n"
        "  - Apple\n"
        "  - mango\n"
        "---\n"
        "# Body content\n"
    )
    path = tmp_prd_dir / "PRD-070-test.md"
    path.write_text(raw, encoding="utf-8")
    normalize_list_field_at(path, "tags", ["zebra", "Apple", "mango"])
    after = path.read_text(encoding="utf-8")
    # Only the tags block should change; verify via exact expected string.
    expected = raw.replace(
        "tags:\n  - zebra\n  - Apple\n  - mango\n",
        "tags:\n  - Apple\n  - mango\n  - zebra\n",
    )
    assert after == expected, "only the tags block should change"


def test_normalize_list_field_at_no_change_when_canonical(tmp_prd_dir: Path) -> None:
    """AC-4: returns False when the field is already in canonical order."""
    raw = '---\nid: "PRD-070"\ntags:\n  - alpha\n  - beta\n  - gamma\n---\nbody\n'
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text(raw, encoding="utf-8")
    changed = normalize_list_field_at(path, "tags", ["alpha", "beta", "gamma"])
    assert not changed
    assert path.read_text(encoding="utf-8") == raw


def test_normalize_list_field_at_rejects_nonempty_flow_style(
    tmp_prd_dir: Path,
) -> None:
    """AC-6: flow-style non-empty list raises a clear ValueError."""
    raw = '---\nid: "PRD-070"\ntags: [foo, bar]\n---\nbody\n'
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="flow-style"):
        normalize_list_field_at(path, "tags", ["foo", "bar"])


def test_normalize_list_field_at_empty_list_writes_flow_empty(
    tmp_prd_dir: Path,
) -> None:
    """Normalizing a non-empty field to an empty list writes ``field: []``."""
    raw = '---\nid: "PRD-070"\ntags:\n  - foo\n---\nbody\n'
    path = tmp_prd_dir / "PRD-070-x.md"
    path.write_text(raw, encoding="utf-8")
    changed = normalize_list_field_at(path, "tags", [])
    assert changed
    after = path.read_text(encoding="utf-8")
    assert "tags: []\n" in after


def test_normalize_list_field_at_write_false_does_not_modify(
    tmp_prd_dir: Path,
) -> None:
    """``write=False`` returns True when changes would occur but does not write."""
    raw = '---\nid: "PRD-070"\ntags:\n  - zebra\n  - Apple\n---\n# Body\n'
    path = tmp_prd_dir / "PRD-070-test.md"
    path.write_text(raw, encoding="utf-8")
    would_change = normalize_list_field_at(
        path, "tags", ["zebra", "Apple"], write=False
    )
    assert would_change
    assert path.read_text(encoding="utf-8") == raw  # file untouched
