"""Tests for ancestor feature extraction via actual preprocessing."""

from __future__ import annotations

from logic.features import zones
from logic.preprocess import preprocess


def test_blockquote_ancestor_fires():
    """A paragraph nested inside a blockquote gets ANCESTOR_BLOCKQUOTE."""
    text = "> A quoted paragraph.\n"
    doc = preprocess(text)
    para_segs = [s for s in doc.segments if "blockquote" in s.ancestors]
    assert para_segs, "Expected at least one segment with blockquote ancestor"
    feats = zones.extract(para_segs[0])
    assert "ANCESTOR_BLOCKQUOTE" in feats


def test_top_level_paragraph_has_no_ancestor():
    """A top-level paragraph does not get any ANCESTOR_* feature."""
    text = "A simple paragraph.\n"
    doc = preprocess(text)
    para_segs = [s for s in doc.segments if s.kind == "paragraph"]
    assert para_segs
    feats = zones.extract(para_segs[0])
    assert not any(f.startswith("ANCESTOR_") for f in feats)


def test_list_bullet_ancestor_fires():
    """Content inside a bullet list gets ANCESTOR_LIST."""
    text = "- A bullet item\n"
    doc = preprocess(text)
    list_segs = [s for s in doc.segments if s.kind == "list_bullet"]
    assert list_segs, "Expected at least one list_bullet segment"
    feats = zones.extract(list_segs[0])
    assert "ANCESTOR_LIST" in feats


def test_paragraph_inside_blockquote_inside_bullet():
    """A paragraph inside a blockquote inside a bullet gets both ANCESTOR_* features."""
    text = "- A bullet item\n\n  > A quoted line inside the bullet.\n"
    doc = preprocess(text)
    # The quoted paragraph has both list_bullet and blockquote as ancestors.
    nested = [
        s for s in doc.segments
        if "blockquote" in s.ancestors and "list_bullet" in s.ancestors
    ]
    assert nested, f"Expected nested segment; got {[s.ancestors for s in doc.segments]}"
    feats = zones.extract(nested[0])
    assert "ANCESTOR_BLOCKQUOTE" in feats
    assert "ANCESTOR_LIST" in feats
