"""Multi-token pattern feature extractor (Phase 2).

Emits PATTERN_* features via regex patterns that span multiple tokens or
require structural context (e.g. segment kind).
"""

from __future__ import annotations

import re

from logic.preprocess import Segment

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Numeric range: 1–10, 1-10, 1 to 10 (including decimal variants)
_NUMERIC_RANGE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:–|—|\-|to)\s*\d+(?:[.,]\d+)?\b",
    re.IGNORECASE,
)

# Citation in parentheses containing a 4-digit year: (Smith 2023), (Act 1999)
_CITATION_PARENS_RE = re.compile(r"\([^()]{2,80}\b\d{4}\b[^()]{0,20}\)")

# Markdown heading prefix
_HEADING_PREFIX_RE = re.compile(r"^#+\s*")

# Stop words that are acceptable in lowercase within a title-case heading
_TITLE_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "but", "or", "for", "nor", "on", "at",
        "to", "by", "in", "of", "up", "as", "is", "with", "from", "into",
        "about", "across", "after", "before", "between", "during",
        "through", "via",
    }
)

# Regnal numeral shape: "George III", "Elizabeth II" (proper noun + Roman numeral)
_REGNAL_RE = re.compile(
    r"\b[A-Z][a-z]+\s+(?:I{2,3}|IV|VI{0,3}|IX|X(?:I{0,3}|IV|V|IX)?|V(?:I{0,3})?)\b"
)

# Leading list markers for bullet/numbered segments
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")


def _heading_text(segment_text: str) -> str:
    """Strip leading # markers and return the bare heading string."""
    return _HEADING_PREFIX_RE.sub("", segment_text).strip()


def _is_title_case_heading(text: str) -> bool:
    """True when ≥2 non-stop significant words after the first have initial caps."""
    words = text.split()
    if len(words) < 2:
        return False
    # Count words from position 1 onwards that have initial capitals and are
    # not common stop words.
    cap_non_stop = sum(
        1
        for w in words[1:]
        if w and w[0].isupper() and w.lower().rstrip(".,;:!?") not in _TITLE_STOP_WORDS
    )
    return cap_non_stop >= 2


def _is_sentence_case_heading(text: str) -> bool:
    """True when the majority of non-first words start with a lowercase letter."""
    words = text.split()
    if len(words) < 2:
        return True  # single-word heading is sentence case by definition
    non_first = words[1:]
    lowercase_count = sum(1 for w in non_first if w and w[0].islower())
    return lowercase_count >= len(non_first) * 0.5


def extract(segment: Segment) -> frozenset[str]:
    """Return pattern features for *segment*."""
    features: set[str] = set()
    text = segment.text

    if _NUMERIC_RANGE_RE.search(text):
        features.add("PATTERN_NUMERIC_RANGE")

    if _CITATION_PARENS_RE.search(text):
        features.add("PATTERN_CITATION_PARENS")

    if segment.kind == "heading":
        bare = _heading_text(text)
        if _is_title_case_heading(bare):
            features.add("PATTERN_HEADING_TITLE_CASE")
        if _is_sentence_case_heading(bare):
            features.add("PATTERN_HEADING_SENTENCE_CASE")

    if segment.kind in ("list_bullet", "list_numbered"):
        # Strip the leading list marker, then check for trailing period.
        bare = _LIST_MARKER_RE.sub("", text.strip()).rstrip()
        if bare.endswith("."):
            features.add("PATTERN_BULLET_ENDS_WITH_PERIOD")

    if _REGNAL_RE.search(text):
        features.add("PATTERN_REGNAL_NUMERAL_SHAPE")

    return frozenset(features)
