"""Tests for the Phase 0 feature vocabulary and validator."""

from __future__ import annotations

import pytest

from logic.features.vocabulary import (
    ANCESTOR_BLOCKQUOTE,
    EXEMPT_FEATURES,
    EXEMPT_URL,
    FEATURE_VOCABULARY,
    REL_BULLET_AFTER_COLON,
    ZONE_PARAGRAPH,
    validate_feature,
)


def test_constants_match_their_names():
    assert ZONE_PARAGRAPH == "ZONE_PARAGRAPH"
    assert ANCESTOR_BLOCKQUOTE == "ANCESTOR_BLOCKQUOTE"
    assert EXEMPT_URL == "EXEMPT_URL"
    assert REL_BULLET_AFTER_COLON == "REL_BULLET_AFTER_COLON"


def test_exempt_features_is_subset_of_vocabulary():
    assert EXEMPT_FEATURES <= FEATURE_VOCABULARY
    assert all(name.startswith("EXEMPT_") for name in EXEMPT_FEATURES)
    assert EXEMPT_URL in EXEMPT_FEATURES


def test_validate_feature_accepts_known_names():
    for name in ["ZONE_HEADING", "HAS_URL", "LING_PASSIVE_VOICE",
                 "PATTERN_NUMERIC_RANGE", "REL_BULLET_AFTER_COLON",
                 "APS_DEPARTMENT_NAME", "EXEMPT_CODE_SNIPPET",
                 "DOC_HAS_HEADINGS"]:
        validate_feature(name)  # must not raise


def test_validate_feature_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown feature"):
        validate_feature("NOT_A_REAL_FEATURE")


@pytest.mark.parametrize(
    "name",
    [
        "LING_LONG_SENTENCE_25P",
        "HAS_CARDINAL_GE_3",
        "LING_MODAL_VERB_LT2",
        "LING_LONG_SENTENCE_25",
        "FOO_GT_5",
    ],
)
def test_validate_feature_rejects_threshold_suffixes(name: str):
    with pytest.raises(ValueError, match="threshold"):
        validate_feature(name)
