"""Tests for logic.features.patterns — PATTERN_* features."""

from __future__ import annotations

import pytest

from logic.features import patterns
from logic.preprocess import Segment


def _seg(text: str, kind: str = "paragraph") -> Segment:
    return Segment(kind=kind, text=text, offset=0, lintable=True)


def _has(feature: str, text: str, kind: str = "paragraph") -> bool:
    return feature in patterns.extract(_seg(text, kind))


# ---------------------------------------------------------------------------
# PATTERN_NUMERIC_RANGE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Refer to pages 10–20 for details.", True),
        ("Refer to pages 10-20 for details.", True),
        ("Refer to pages 10 to 20 for details.", True),
        ("Refer to the relevant pages.", False),
    ],
)
def test_numeric_range(text, expected):
    assert _has("PATTERN_NUMERIC_RANGE", text) == expected


# ---------------------------------------------------------------------------
# PATTERN_CITATION_PARENS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This is consistent with the Act (Smith 2022).", True),
        ("This is consistent with the Act (as amended 2019).", True),
        ("This is consistent with the Act.", False),
        ("See (b) for details.", False),  # no year
    ],
)
def test_citation_parens(text, expected):
    assert _has("PATTERN_CITATION_PARENS", text) == expected


# ---------------------------------------------------------------------------
# PATTERN_HEADING_TITLE_CASE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("## The Australian Government Policy Framework", True),
        ("## How to Submit Your Form", True),
        ("## How to submit your form", False),
        ("## Heading", False),  # single word after stripping, no run of 2+
    ],
)
def test_heading_title_case(text, expected):
    assert _has("PATTERN_HEADING_TITLE_CASE", text, kind="heading") == expected


# ---------------------------------------------------------------------------
# PATTERN_HEADING_SENTENCE_CASE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("## How to submit your form", True),
        ("## Australian Government services for citizens", True),
        ("## THE WRONG HEADING", False),
    ],
)
def test_heading_sentence_case(text, expected):
    assert _has("PATTERN_HEADING_SENTENCE_CASE", text, kind="heading") == expected


def test_heading_patterns_only_fire_on_heading_kind():
    """PATTERN_HEADING_* does NOT fire for paragraph segments."""
    text = "## How to Submit Your Form"
    assert not _has("PATTERN_HEADING_TITLE_CASE", text, kind="paragraph")
    assert not _has("PATTERN_HEADING_SENTENCE_CASE", text, kind="paragraph")


# ---------------------------------------------------------------------------
# PATTERN_BULLET_ENDS_WITH_PERIOD
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("- Complete the form.", True),
        ("- Complete the form", False),
        ("- Complete the form:", False),
    ],
)
def test_bullet_ends_with_period(text, expected):
    assert _has("PATTERN_BULLET_ENDS_WITH_PERIOD", text, kind="list_bullet") == expected


def test_bullet_period_only_fires_on_list_kinds():
    """Does NOT fire on a paragraph segment even with trailing period."""
    assert not _has("PATTERN_BULLET_ENDS_WITH_PERIOD", "A sentence.", kind="paragraph")


# ---------------------------------------------------------------------------
# PATTERN_REGNAL_NUMERAL_SHAPE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The reign of George III was significant.", True),
        ("Elizabeth II signed the proclamation.", True),
        ("The reign was significant.", False),
    ],
)
def test_regnal_numeral(text, expected):
    assert _has("PATTERN_REGNAL_NUMERAL_SHAPE", text) == expected
