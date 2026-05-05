"""Integration tests for logic.features.extractor.

The Step 1 snapshot test locks down the full feature set for the noisy
"Step 1 — Merge this branch to main" example as a regression anchor.
"""

from __future__ import annotations

import pytest

from logic.features.extractor import FeatureSet, extract
from logic.preprocess import preprocess


@pytest.fixture(scope="module")
def nlp():
    import spacy
    return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])


# ---------------------------------------------------------------------------
# Smoke test: extract returns a FeatureSet
# ---------------------------------------------------------------------------


def test_extract_returns_feature_set(nlp):
    doc = preprocess("The minister announced the new policy.")
    fs = extract(doc, nlp)
    assert isinstance(fs, FeatureSet)
    assert isinstance(fs.document, frozenset)
    assert isinstance(fs.per_segment, list)
    assert len(fs.per_segment) == len(doc.segments)


def test_per_segment_aligned_to_segments(nlp):
    doc = preprocess("# Heading\n\nA paragraph.\n")
    fs = extract(doc, nlp)
    assert len(fs.per_segment) == len(doc.segments)


# ---------------------------------------------------------------------------
# Step 1 noisy example — regression snapshot
# ---------------------------------------------------------------------------

_STEP1_TEXT = (
    "Step 1 — Merge this branch to main\n"
    "The changes just pushed need to be on main before Render deploys them."
)

_STEP1_EXPECTED_DOCUMENT = frozenset(
    {
        "DOC_LANGUAGE_EN",
        "EXEMPT_BRANCHNAME",
        "EXEMPT_PRODUCT_NAME",
    }
)

_STEP1_EXPECTED_SEG0 = frozenset(
    {
        "EXEMPT_BRANCHNAME",
        "EXEMPT_PRODUCT_NAME",
        "HAS_CARDINAL",
        "HAS_EM_DASH",
        "LING_PROPER_NOUN",
        "ZONE_PARAGRAPH",
    }
)


def test_step1_document_has_required_exemptions(nlp):
    """Must include EXEMPT_BRANCHNAME and EXEMPT_PRODUCT_NAME."""
    doc = preprocess(_STEP1_TEXT)
    fs = extract(doc, nlp)
    assert "EXEMPT_BRANCHNAME" in fs.document
    assert "EXEMPT_PRODUCT_NAME" in fs.document


def test_step1_document_snapshot(nlp):
    """Regression: document feature set is exactly the expected frozenset."""
    doc = preprocess(_STEP1_TEXT)
    fs = extract(doc, nlp)
    assert fs.document == _STEP1_EXPECTED_DOCUMENT


def test_step1_segment_snapshot(nlp):
    """Regression: segment 0 feature set is exactly the expected frozenset."""
    doc = preprocess(_STEP1_TEXT)
    fs = extract(doc, nlp)
    assert fs.per_segment[0] == _STEP1_EXPECTED_SEG0


# ---------------------------------------------------------------------------
# Heading + list structural test
# ---------------------------------------------------------------------------


def test_heading_followed_by_list(nlp):
    text = "## Requirements\n\n- Item one\n- Item two\n"
    doc = preprocess(text)
    fs = extract(doc, nlp)
    assert "DOC_HAS_HEADINGS" in fs.document
    assert "DOC_HAS_LISTS" in fs.document
    heading_feats = next(
        feats for seg, feats in zip(doc.segments, fs.per_segment)
        if seg.kind == "heading"
    )
    assert "ZONE_HEADING" in heading_feats
    assert "REL_HEADING_FOLLOWED_BY_LIST" in heading_feats


# ---------------------------------------------------------------------------
# Undeclared feature raises ValueError
# ---------------------------------------------------------------------------


def test_undeclared_feature_raises(nlp, monkeypatch):
    """A sub-extractor emitting an unknown feature name causes extract() to raise."""
    import logic.features.zones as zones_mod

    original = zones_mod.extract

    def bad_extract(segment):
        return frozenset({"ZONE_FAKE"})

    monkeypatch.setattr(zones_mod, "extract", bad_extract)
    try:
        doc = preprocess("# Hello\nTest.")
        with pytest.raises(ValueError, match="Unknown feature"):
            extract(doc, nlp)
    finally:
        monkeypatch.setattr(zones_mod, "extract", original)
