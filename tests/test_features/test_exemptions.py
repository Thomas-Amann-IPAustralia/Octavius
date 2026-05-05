"""Tests for logic.features.exemptions — EXEMPT_* features from mask_map."""

from __future__ import annotations

from logic.features import exemptions
from logic.preprocess import preprocess


def test_url_exempt_in_segment():
    doc = preprocess("See https://example.gov.au for details.")
    para_seg = next(s for s in doc.segments if s.lintable)
    feats = exemptions.extract_for_segment(para_seg, doc.mask_map)
    assert "EXEMPT_URL" in feats


def test_url_exempt_in_document():
    doc = preprocess("See https://example.gov.au for details.")
    feats = exemptions.extract_for_document(doc.mask_map)
    assert "EXEMPT_URL" in feats


def test_branchname_exempt_in_segment():
    doc = preprocess("Merge to main when ready.")
    para_seg = next(s for s in doc.segments if s.lintable)
    feats = exemptions.extract_for_segment(para_seg, doc.mask_map)
    assert "EXEMPT_BRANCHNAME" in feats


def test_masked_url_in_both_segment_and_document():
    """EXEMPT_URL fires in the containing segment AND in the document feature set."""
    doc = preprocess("Read the policy at https://example.gov.au today.")
    para_seg = next(s for s in doc.segments if s.kind == "paragraph")
    seg_feats = exemptions.extract_for_segment(para_seg, doc.mask_map)
    doc_feats = exemptions.extract_for_document(doc.mask_map)
    assert "EXEMPT_URL" in seg_feats
    assert "EXEMPT_URL" in doc_feats


def test_code_snippet_exempt_in_segment():
    doc = preprocess("Run `pytest -v` to execute the tests.")
    inline_segs = [s for s in doc.segments if s.kind == "inline_code"]
    # The code_snippet mask falls within the paragraph's range
    para_seg = next(s for s in doc.segments if s.kind == "paragraph")
    feats = exemptions.extract_for_segment(para_seg, doc.mask_map)
    assert "EXEMPT_CODE_SNIPPET" in feats


def test_identifier_exempt():
    doc = preprocess("The variable user_name_value is used.")
    doc_feats = exemptions.extract_for_document(doc.mask_map)
    assert "EXEMPT_IDENTIFIER" in doc_feats


def test_no_exempt_for_plain_prose():
    doc = preprocess("The minister announced the new policy today.")
    doc_feats = exemptions.extract_for_document(doc.mask_map)
    exempt_feats = {f for f in doc_feats if f.startswith("EXEMPT_")}
    # Plain prose with no masked regions has no exemption features
    # (except possibly EXEMPT_PRODUCT_NAME for title-case words)
    assert "EXEMPT_URL" not in exempt_feats
    assert "EXEMPT_CODE_SNIPPET" not in exempt_feats


def test_product_name_exempt_appears_in_document():
    """Render is masked as product_name mid-sentence."""
    doc = preprocess(
        "The changes need to be deployed before Render picks them up."
    )
    doc_feats = exemptions.extract_for_document(doc.mask_map)
    assert "EXEMPT_PRODUCT_NAME" in doc_feats
