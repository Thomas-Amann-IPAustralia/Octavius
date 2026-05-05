"""Feature vocabulary for the inverted-index dispatcher.

Architectural rules
-------------------
1. Thresholds must NEVER appear in feature names. A feature is a boolean
   observation about a segment or document — anything that needs a numeric
   threshold (e.g. "more than 25 words") belongs in extractor parameters,
   not in the feature name.

2. Numeric counts live on ``PreprocessedDoc.counts: dict[str, int]`` (added
   in Phase 1) and are not features in this phase. Phase 0 only ships the
   boolean feature vocabulary; rules that need count-based gating will be
   handled by a future ``min_count`` slot on ``FeatureRequirements``.

The validator below also guards against accidental reintroduction of
threshold-bearing names by rejecting anything matching the regex
``r"_(GE|GT|LT|LE)?_?\\d+P?$"`` (e.g. ``LING_LONG_SENTENCE_25P``).
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

FEATURE_VOCABULARY: Final[frozenset[str]] = frozenset({
    # Structural — segment's own kind
    "ZONE_HEADING",
    "ZONE_PARAGRAPH",
    "ZONE_LIST_BULLET",
    "ZONE_LIST_NUMBERED",
    "ZONE_TABLE_CELL",
    "ZONE_BLOCKQUOTE",
    "ZONE_CODE_FENCE",
    "ZONE_INLINE_CODE",
    "ZONE_FOOTNOTE",
    "ZONE_REFERENCE_LIST",

    # Segment lineage
    "ANCESTOR_BLOCKQUOTE",
    "ANCESTOR_LIST",
    "ANCESTOR_TABLE",
    "ANCESTOR_FOOTNOTE",
    "ANCESTOR_HEADING_SECTION",

    # Lexical observations
    "HAS_CARDINAL",
    "HAS_ORDINAL",
    "HAS_PERCENT",
    "HAS_CURRENCY",
    "HAS_DATE",
    "HAS_TIME",
    "HAS_URL",
    "HAS_EMAIL",
    "HAS_ABBREVIATION",
    "HAS_ACRONYM",
    "HAS_ROMAN_NUMERAL",
    "HAS_EM_DASH",
    "HAS_EN_DASH",
    "HAS_HYPHEN",
    "HAS_COLON",
    "HAS_SEMICOLON",
    "HAS_STRAIGHT_QUOTE",
    "HAS_CURLY_QUOTE",
    "HAS_DOUBLE_SPACE",
    "HAS_PARENTHESES",

    # Linguistic — thresholds live in extractor parameters
    "LING_PASSIVE_VOICE",
    "LING_MODAL_VERB",
    "LING_FIRST_PERSON",
    "LING_SECOND_PERSON",
    "LING_IMPERATIVE",
    "LING_PROPER_NOUN",
    "LING_TITLE_CASE_SEQUENCE",
    "LING_ALL_CAPS_TOKEN",
    "LING_NEGATION",
    "LING_LONG_SENTENCE",

    # Multi-token patterns — deliberately small starter set
    "PATTERN_NUMERIC_RANGE",
    "PATTERN_CITATION_PARENS",
    "PATTERN_HEADING_TITLE_CASE",
    "PATTERN_HEADING_SENTENCE_CASE",
    "PATTERN_BULLET_ENDS_WITH_PERIOD",
    "PATTERN_REGNAL_NUMERAL_SHAPE",

    # Cross-segment relations — tightly scoped
    "REL_BULLET_AFTER_COLON",
    "REL_ACRONYM_DEFINED_ON_FIRST_USE",
    "REL_HEADING_FOLLOWED_BY_LIST",
    "REL_CITATION_AFTER_QUOTE",

    # Domain-specific lookups
    "APS_LEGISLATION_REFERENCE",
    "APS_DEPARTMENT_NAME",
    "APS_MINISTERIAL_TITLE",
    "APS_DATE_LONGFORM",
    "APS_COMMONWEALTH_ENTITY",

    # Exemptions — only used in a rule's `none_of` slot
    "EXEMPT_URL",
    "EXEMPT_FILEPATH",
    "EXEMPT_BRANCHNAME",
    "EXEMPT_IDENTIFIER",
    "EXEMPT_ENV_VAR",
    "EXEMPT_PRODUCT_NAME",
    "EXEMPT_MENTION_OR_HASHTAG",
    "EXEMPT_CODE_SNIPPET",
    "EXEMPT_QUOTED_CONTENT",

    # Document-scope booleans only
    "DOC_HAS_HEADINGS",
    "DOC_HAS_LISTS",
    "DOC_HAS_CITATIONS",
    "DOC_LANGUAGE_EN",
})


EXEMPT_FEATURES: Final[frozenset[str]] = frozenset({
    name for name in FEATURE_VOCABULARY if name.startswith("EXEMPT_")
})


# ---------------------------------------------------------------------------
# Re-exports of individual feature constants
# ---------------------------------------------------------------------------
# Each vocabulary entry is also exposed as a module-level string constant
# (``ZONE_HEADING = "ZONE_HEADING"`` etc.) so that callers can write
# ``from logic.features.vocabulary import ZONE_HEADING`` and get static
# lookups + autocomplete instead of stringly-typed magic.
for _name in FEATURE_VOCABULARY:
    globals()[_name] = _name
del _name


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Regression guard: feature names must not encode numeric thresholds.
# Examples that must be rejected: ``LING_LONG_SENTENCE_25P``,
# ``HAS_CARDINAL_GE_3``, ``LING_MODAL_VERB_LT2``.
_THRESHOLD_SUFFIX_RE: Final = re.compile(r"_(GE|GT|LT|LE)?_?\d+P?$")


def validate_feature(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a valid feature.

    A name is invalid if it is not in :data:`FEATURE_VOCABULARY`, or if it
    matches the threshold-suffix regression guard regex.
    """
    if _THRESHOLD_SUFFIX_RE.search(name):
        raise ValueError(
            f"Feature name {name!r} encodes a numeric threshold; thresholds "
            "must live in extractor parameters, not feature names."
        )
    if name not in FEATURE_VOCABULARY:
        raise ValueError(f"Unknown feature name: {name!r}")
