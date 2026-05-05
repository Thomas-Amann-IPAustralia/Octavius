"""Tests for logic.features.relations — REL_* features."""

from __future__ import annotations

import pytest

from logic.features import relations
from logic.preprocess import preprocess


def _rel(text: str) -> list[frozenset[str]]:
    doc = preprocess(text)
    return relations.extract(doc)


# ---------------------------------------------------------------------------
# REL_BULLET_AFTER_COLON
# ---------------------------------------------------------------------------


def test_bullet_after_colon_fires():
    """First bullet after a colon-ending paragraph gets REL_BULLET_AFTER_COLON."""
    doc = preprocess("The requirements are:\n\n- First item\n- Second item\n")
    rel_feats = relations.extract(doc)
    list_segs = [
        (seg, feats)
        for seg, feats in zip(doc.segments, rel_feats)
        if seg.kind == "list_bullet"
    ]
    assert list_segs, "Expected list_bullet segments"
    first_bullet_feats = list_segs[0][1]
    assert "REL_BULLET_AFTER_COLON" in first_bullet_feats


def test_bullet_after_colon_second_bullet_does_not_fire():
    """Subsequent bullets (not immediately after the colon paragraph) do not fire."""
    doc = preprocess("The requirements are:\n\n- First item\n- Second item\n")
    rel_feats = relations.extract(doc)
    list_segs = [
        feats
        for seg, feats in zip(doc.segments, rel_feats)
        if seg.kind == "list_bullet"
    ]
    assert len(list_segs) >= 2
    # Second and later bullets do not have REL_BULLET_AFTER_COLON
    assert "REL_BULLET_AFTER_COLON" not in list_segs[1]


def test_bullet_not_after_colon_does_not_fire():
    """A bullet that follows a non-colon paragraph does NOT get REL_BULLET_AFTER_COLON."""
    doc = preprocess("Here is a paragraph with no colon\n\n- Item one\n- Item two\n")
    rel_feats = relations.extract(doc)
    bullet_feats = [
        feats
        for seg, feats in zip(doc.segments, rel_feats)
        if seg.kind == "list_bullet"
    ]
    assert bullet_feats, "Expected list_bullet segments"
    for feats in bullet_feats:
        assert "REL_BULLET_AFTER_COLON" not in feats


# ---------------------------------------------------------------------------
# REL_ACRONYM_DEFINED_ON_FIRST_USE
# ---------------------------------------------------------------------------


def test_acronym_defined_fires():
    """A segment containing 'Full Name (ACRO)' gets REL_ACRONYM_DEFINED_ON_FIRST_USE."""
    doc = preprocess(
        "The Australian Public Service (APS) provides guidance on plain language."
    )
    rel_feats = relations.extract(doc)
    any_fired = any("REL_ACRONYM_DEFINED_ON_FIRST_USE" in feats for feats in rel_feats)
    assert any_fired


def test_acronym_defined_not_present():
    """A segment with a standalone acronym (no definition) does not fire."""
    doc = preprocess("The APS provides guidance on plain language.")
    rel_feats = relations.extract(doc)
    any_fired = any("REL_ACRONYM_DEFINED_ON_FIRST_USE" in feats for feats in rel_feats)
    assert not any_fired


# ---------------------------------------------------------------------------
# REL_HEADING_FOLLOWED_BY_LIST
# ---------------------------------------------------------------------------


def test_heading_followed_by_list_fires():
    """A heading immediately followed by a list gets REL_HEADING_FOLLOWED_BY_LIST."""
    doc = preprocess("## Requirements\n\n- Item one\n- Item two\n")
    rel_feats = relations.extract(doc)
    heading_feats = [
        feats
        for seg, feats in zip(doc.segments, rel_feats)
        if seg.kind == "heading"
    ]
    assert heading_feats
    assert "REL_HEADING_FOLLOWED_BY_LIST" in heading_feats[0]


def test_heading_followed_by_paragraph_does_not_fire():
    """A heading followed by a paragraph does NOT get REL_HEADING_FOLLOWED_BY_LIST."""
    doc = preprocess("## Introduction\n\nThis is a paragraph.\n")
    rel_feats = relations.extract(doc)
    heading_feats = [
        feats
        for seg, feats in zip(doc.segments, rel_feats)
        if seg.kind == "heading"
    ]
    assert heading_feats
    assert "REL_HEADING_FOLLOWED_BY_LIST" not in heading_feats[0]


# ---------------------------------------------------------------------------
# REL_CITATION_AFTER_QUOTE
# ---------------------------------------------------------------------------


def test_citation_after_quote_fires():
    """A citation pattern within ~50 chars of a quoted region fires REL_CITATION_AFTER_QUOTE."""
    doc = preprocess('The minister said "plain language matters" (Smith 2020).')
    rel_feats = relations.extract(doc)
    any_fired = any("REL_CITATION_AFTER_QUOTE" in feats for feats in rel_feats)
    assert any_fired


def test_citation_after_quote_no_citation():
    """A quote not followed by a citation does NOT fire REL_CITATION_AFTER_QUOTE."""
    doc = preprocess('The minister said "plain language matters" at the conference.')
    rel_feats = relations.extract(doc)
    any_fired = any("REL_CITATION_AFTER_QUOTE" in feats for feats in rel_feats)
    assert not any_fired
