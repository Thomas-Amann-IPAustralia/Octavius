"""Lexical feature extractor (Phase 2).

Emits HAS_* features by running compiled regex patterns over the raw segment
text.  Each feature fires when the pattern matches at least once.
"""

from __future__ import annotations

import re

from logic.preprocess import Segment

# ---------------------------------------------------------------------------
# Compiled patterns — ordered for readability, not performance
# ---------------------------------------------------------------------------

_CHECKS: list[tuple[str, re.Pattern[str]]] = [
    # Cardinal numbers (including comma-grouped figures like 1,000)
    ("HAS_CARDINAL", re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")),
    # Ordinals: 1st, 2nd, 3rd, 4th …
    ("HAS_ORDINAL", re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)),
    # Percentages: 25%, 3.5%, "25 per cent"
    (
        "HAS_PERCENT",
        re.compile(
            r"\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*per\s+cent\b",
            re.IGNORECASE,
        ),
    ),
    # Currency symbols before or after a number
    ("HAS_CURRENCY", re.compile(r"(?:AU\$|A\$|USD|\$|€|£|¥)\s*[\d,]+|\b[\d,]+\s*(?:AU\$|A\$|USD)")),
    # Dates: DD/MM/YYYY, YYYY-MM-DD, "1 January 2024"
    (
        "HAS_DATE",
        re.compile(
            r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b"
            r"|\b\d{4}[/\-]\d{2}[/\-]\d{2}\b"
            r"|\b\d{1,2}\s+(?:January|February|March|April|May|June|July"
            r"|August|September|October|November|December)\s+\d{4}\b",
            re.IGNORECASE,
        ),
    ),
    # Times: 9:30, 9:30am, 14:00
    ("HAS_TIME", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)\b", re.IGNORECASE)),
    # URLs
    ("HAS_URL", re.compile(r"https?://\S+|www\.\S+")),
    # Email addresses
    ("HAS_EMAIL", re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    # Common abbreviations (e.g., i.e., etc., et al., vs., fig., no., op. cit.)
    (
        "HAS_ABBREVIATION",
        re.compile(
            r"\b(?:e\.g\.|i\.e\.|etc\.|et\s+al\.|vs\.|fig\.|no\.|op\.cit\."
            r"|cf\.|ibid\.|loc\.cit\.|p\.\s*\d|pp\.\s*\d)",
            re.IGNORECASE,
        ),
    ),
    # Acronyms: 2+ consecutive uppercase letters (word-bounded)
    ("HAS_ACRONYM", re.compile(r"\b[A-Z]{2,}\b")),
    # Roman numerals: 2–8-char sequences of IVXLCDM (case-insensitive)
    ("HAS_ROMAN_NUMERAL", re.compile(r"\b[IVXLCDMivxlcdm]{2,8}\b")),
    # Em dash
    ("HAS_EM_DASH", re.compile("—")),
    # En dash
    ("HAS_EN_DASH", re.compile("–")),
    # Hyphenated compound: word-word
    ("HAS_HYPHEN", re.compile(r"\b\w+\-\w+\b")),
    # Colon
    ("HAS_COLON", re.compile(r":")),
    # Semicolon
    ("HAS_SEMICOLON", re.compile(r";")),
    # Straight single or double quote characters
    ("HAS_STRAIGHT_QUOTE", re.compile(r"""[\"']""")),
    # Curly / typographic quotes (both pairs: U+201C/D and U+2018/9)
    ("HAS_CURLY_QUOTE", re.compile("[“”‘’]")),
    # Two or more consecutive spaces
    ("HAS_DOUBLE_SPACE", re.compile(r"  ")),
    # Any opening or closing parenthesis
    ("HAS_PARENTHESES", re.compile(r"[()]")),
]


def extract(segment: Segment) -> frozenset[str]:
    """Return lexical features for *segment* by matching against its text."""
    features: set[str] = set()
    text = segment.text
    for feature_name, pattern in _CHECKS:
        if pattern.search(text):
            features.add(feature_name)
    return frozenset(features)
