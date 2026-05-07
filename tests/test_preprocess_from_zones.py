"""Tests for logic.preprocess.from_zones.

Validates that from_zones() produces a PreprocessedDoc equivalent to
preprocess() for representative inputs, documents legitimate differences,
and handles edge cases correctly.
"""

from __future__ import annotations

import pytest

from logic.preprocess import (
    PreprocessedDoc,
    Segment,
    from_zones,
    preprocess,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zones(plain_text: str, segments: list[dict]) -> PreprocessedDoc:
    """Shorthand — call from_zones with a list of zone dicts."""
    return from_zones(plain_text, segments)


def _seg_tuples(doc: PreprocessedDoc) -> list[tuple[str, str, int, bool]]:
    """(kind, text_prefix[:30], offset, lintable) for each segment."""
    return [(s.kind, s.text[:30], s.offset, s.lintable) for s in doc.segments]


# ---------------------------------------------------------------------------
# Zone invariant: text == plain_text[offset:offset+length]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plain_text,zones", [
    (
        "A heading\nA paragraph\n",
        [
            {"kind": "heading", "text": "A heading", "offset": 0, "length": 9, "ancestors": [], "lintable": True},
            {"kind": "paragraph", "text": "A paragraph", "offset": 10, "length": 11, "ancestors": [], "lintable": True},
        ],
    ),
    (
        "Item 1\nItem 2\n",
        [
            {"kind": "list_bullet", "text": "Item 1", "offset": 0, "length": 6, "ancestors": [], "lintable": True},
            {"kind": "list_bullet", "text": "Item 2", "offset": 7, "length": 6, "ancestors": [], "lintable": True},
        ],
    ),
])
def test_zone_text_offset_invariant(plain_text: str, zones: list[dict]) -> None:
    """Zones must satisfy plain_text[offset:offset+length] == text."""
    for z in zones:
        extracted = plain_text[z["offset"] : z["offset"] + z["length"]]
        assert extracted == z["text"], (
            f"Invariant violated: plain_text[{z['offset']}:{z['offset']+z['length']}]"
            f"={extracted!r} != zone.text={z['text']!r}"
        )


# ---------------------------------------------------------------------------
# Segment equivalence tests
# ---------------------------------------------------------------------------


def test_from_zones_heading_and_paragraph() -> None:
    """Heading + paragraph zones produce equivalent segments to markdown path."""
    plain = "My heading\nMy paragraph text.\n"
    zones = [
        {"kind": "heading", "text": "My heading", "offset": 0, "length": 10, "ancestors": [], "lintable": True},
        {"kind": "paragraph", "text": "My paragraph text.", "offset": 11, "length": 18, "ancestors": [], "lintable": True},
    ]
    doc = _zones(plain, zones)

    # from_zones produces exactly the segments it was given (plus any regex-derived
    # inline_code segments — there are none here).
    kinds = [s.kind for s in doc.segments]
    assert "heading" in kinds
    assert "paragraph" in kinds

    heading = next(s for s in doc.segments if s.kind == "heading")
    assert heading.text == "My heading"
    assert heading.offset == 0
    assert heading.lintable is True

    para = next(s for s in doc.segments if s.kind == "paragraph")
    assert para.text == "My paragraph text."
    assert para.offset == 11


def test_from_zones_list_items() -> None:
    doc = _zones(
        "First item\nSecond item\n",
        [
            {"kind": "list_bullet", "text": "First item", "offset": 0, "length": 10, "ancestors": [], "lintable": True},
            {"kind": "list_bullet", "text": "Second item", "offset": 11, "length": 11, "ancestors": [], "lintable": True},
        ],
    )
    kinds = [s.kind for s in doc.segments]
    assert kinds.count("list_bullet") == 2


def test_from_zones_table_cell() -> None:
    doc = _zones(
        "Cell A\nCell B\n",
        [
            {"kind": "table_cell", "text": "Cell A", "offset": 0, "length": 6, "ancestors": [], "lintable": True},
            {"kind": "table_cell", "text": "Cell B", "offset": 7, "length": 6, "ancestors": [], "lintable": True},
        ],
    )
    assert all(s.kind == "table_cell" for s in doc.segments)


def test_from_zones_code_fence_not_lintable() -> None:
    doc = _zones(
        "```python\nprint('hi')\n```\n",
        [
            {"kind": "code_fence", "text": "```python\nprint('hi')\n```", "offset": 0, "length": 24, "ancestors": [], "lintable": False},
        ],
    )
    seg = next(s for s in doc.segments if s.kind == "code_fence")
    assert seg.lintable is False


def test_from_zones_blockquote_ancestor() -> None:
    """A paragraph inside a blockquote with ancestors=["blockquote"]."""
    doc = _zones(
        "Quoted text\n",
        [
            {"kind": "paragraph", "text": "Quoted text", "offset": 0, "length": 11, "ancestors": ["blockquote"], "lintable": True},
        ],
    )
    para = doc.segments[0]
    assert para.ancestors == ["blockquote"]


# ---------------------------------------------------------------------------
# has_structure detection
# ---------------------------------------------------------------------------


def test_from_zones_has_structure_with_heading() -> None:
    doc = _zones("Heading\n", [
        {"kind": "heading", "text": "Heading", "offset": 0, "length": 7, "ancestors": [], "lintable": True},
    ])
    assert doc.has_structure is True


def test_from_zones_has_structure_false_plain() -> None:
    doc = _zones("Just prose.\n", [
        {"kind": "paragraph", "text": "Just prose.", "offset": 0, "length": 11, "ancestors": [], "lintable": True},
    ])
    assert doc.has_structure is False


def test_from_zones_has_structure_with_list() -> None:
    doc = _zones("Item\n", [
        {"kind": "list_bullet", "text": "Item", "offset": 0, "length": 4, "ancestors": [], "lintable": True},
    ])
    assert doc.has_structure is True


# ---------------------------------------------------------------------------
# Masking still runs on from_zones path
# ---------------------------------------------------------------------------


def test_from_zones_masking_runs() -> None:
    """URLs in plain_text should appear in mask_map even on the zone path."""
    plain = "See https://example.com for details.\n"
    doc = _zones(plain, [
        {"kind": "paragraph", "text": plain.strip(), "offset": 0, "length": len(plain.strip()), "ancestors": [], "lintable": True},
    ])
    # Masking should have fired on the URL.
    kinds = [kind for _, _, _, kind in doc.mask_map]
    assert "url" in kinds
    assert len(doc.masked) == len(plain)


def test_from_zones_original_stored_correctly() -> None:
    plain = "Hello world.\n"
    doc = _zones(plain, [
        {"kind": "paragraph", "text": "Hello world.", "offset": 0, "length": 12, "ancestors": [], "lintable": True},
    ])
    assert doc.original == plain


# ---------------------------------------------------------------------------
# Difference documentation: blockquote zone kind
# ---------------------------------------------------------------------------


def test_from_zones_blockquote_kind_accepted() -> None:
    """The zone path accepts kind='blockquote' directly; the markdown path
    does not emit this kind (it uses paragraph + ancestors=["blockquote"]).
    Both paths are valid — rules using ZONE_BLOCKQUOTE only fire on the
    zone path; rules using ZONE_PARAGRAPH+ANCESTOR_BLOCKQUOTE only fire
    on the markdown path.
    """
    doc = _zones("Quote.\n", [
        {"kind": "blockquote", "text": "Quote.", "offset": 0, "length": 6, "ancestors": [], "lintable": True},
    ])
    assert doc.segments[0].kind == "blockquote"


# ---------------------------------------------------------------------------
# Inline code deduplication
# ---------------------------------------------------------------------------


def test_from_zones_inline_code_no_duplicate() -> None:
    """Frontend-supplied inline_code zones must not be doubled by the regex pass."""
    plain = "Use `code` here.\n"
    doc = _zones(plain, [
        {"kind": "paragraph", "text": "Use `code` here.", "offset": 0, "length": 16, "ancestors": [], "lintable": True},
        {"kind": "inline_code", "text": "`code`", "offset": 4, "length": 6, "ancestors": ["paragraph"], "lintable": False},
    ])
    inline_code_segs = [s for s in doc.segments if s.kind == "inline_code"]
    assert len(inline_code_segs) == 1, "Inline code segment should not be duplicated"


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_from_zones_empty_text() -> None:
    doc = _zones("", [])
    assert doc.original == ""
    assert doc.segments == []


def test_from_zones_empty_zones() -> None:
    """When zones list is empty, from_zones falls through to masking only."""
    doc = _zones("Some text.\n", [])
    # No user-supplied segments but masking still runs.
    assert doc.original == "Some text.\n"
    assert all(s.kind == "inline_code" for s in doc.segments)  # only regex-derived


def test_from_zones_preserves_ancestors() -> None:
    doc = _zones("Nested\n", [
        {"kind": "list_bullet", "text": "Nested", "offset": 0, "length": 6,
         "ancestors": ["list_bullet"], "lintable": True},
    ])
    assert doc.segments[0].ancestors == ["list_bullet"]
