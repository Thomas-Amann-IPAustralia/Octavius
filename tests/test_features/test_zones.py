"""Tests for logic.features.zones — ZONE_* and ANCESTOR_* features."""

from __future__ import annotations

import pytest

from logic.features import zones
from logic.preprocess import Segment, preprocess


# ---------------------------------------------------------------------------
# ZONE_* from segment.kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,expected_zone",
    [
        ("heading", "ZONE_HEADING"),
        ("paragraph", "ZONE_PARAGRAPH"),
        ("list_bullet", "ZONE_LIST_BULLET"),
        ("list_numbered", "ZONE_LIST_NUMBERED"),
        ("table_cell", "ZONE_TABLE_CELL"),
        ("blockquote", "ZONE_BLOCKQUOTE"),
        ("code_fence", "ZONE_CODE_FENCE"),
        ("inline_code", "ZONE_INLINE_CODE"),
        ("footnote", "ZONE_FOOTNOTE"),
        ("reference_list", "ZONE_REFERENCE_LIST"),
    ],
)
def test_zone_feature_for_kind(kind, expected_zone):
    seg = Segment(kind=kind, text="", offset=0, lintable=True)
    feats = zones.extract(seg)
    assert expected_zone in feats


def test_no_unknown_zone_features():
    """Only one ZONE_* fires per segment and no ANCESTOR_* fires on an orphan."""
    seg = Segment(kind="paragraph", text="Hello.", offset=0, lintable=True)
    feats = zones.extract(seg)
    assert feats == frozenset({"ZONE_PARAGRAPH"})


# ---------------------------------------------------------------------------
# ZONE_HEADING and ZONE_LIST_BULLET appear in document features via extractor
# ---------------------------------------------------------------------------


def test_heading_and_bullet_document_features():
    """A doc with a heading and bullet items has both ZONE_* in its segments."""
    text = "# Heading\n\n- Item one\n- Item two\n"
    doc = preprocess(text)
    seg_zones = set()
    for seg in doc.segments:
        seg_zones.update(zones.extract(seg))
    assert "ZONE_HEADING" in seg_zones
    assert "ZONE_LIST_BULLET" in seg_zones


# ---------------------------------------------------------------------------
# ANCESTOR_* from segment.ancestors
# ---------------------------------------------------------------------------


def test_ancestor_blockquote():
    seg = Segment(
        kind="paragraph", text="Quoted.", offset=0, lintable=True,
        ancestors=["blockquote"],
    )
    feats = zones.extract(seg)
    assert "ANCESTOR_BLOCKQUOTE" in feats


def test_ancestor_list_from_bullet():
    seg = Segment(
        kind="paragraph", text="List item.", offset=0, lintable=True,
        ancestors=["list_bullet"],
    )
    feats = zones.extract(seg)
    assert "ANCESTOR_LIST" in feats


def test_ancestor_list_from_numbered():
    seg = Segment(
        kind="paragraph", text="Item.", offset=0, lintable=True,
        ancestors=["list_numbered"],
    )
    feats = zones.extract(seg)
    assert "ANCESTOR_LIST" in feats


def test_multiple_ancestors():
    seg = Segment(
        kind="paragraph", text="Nested.", offset=0, lintable=True,
        ancestors=["list_bullet", "blockquote"],
    )
    feats = zones.extract(seg)
    assert "ANCESTOR_LIST" in feats
    assert "ANCESTOR_BLOCKQUOTE" in feats


def test_no_ancestor_for_top_level_paragraph():
    seg = Segment(
        kind="paragraph", text="Top-level.", offset=0, lintable=True,
        ancestors=[],
    )
    feats = zones.extract(seg)
    assert not any(f.startswith("ANCESTOR_") for f in feats)
