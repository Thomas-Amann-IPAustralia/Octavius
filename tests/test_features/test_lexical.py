"""Tests for logic.features.lexical — HAS_* features (20 cases each)."""

from __future__ import annotations

import pytest

from logic.features import lexical
from logic.preprocess import Segment


def _seg(text: str) -> Segment:
    return Segment(kind="paragraph", text=text, offset=0, lintable=True)


def _has(feature: str, text: str) -> bool:
    return feature in lexical.extract(_seg(text))


# ---------------------------------------------------------------------------
# Positive + negative cases for each HAS_* feature
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("There are 3 items.", True),
        ("No numbers here at all.", False),
    ],
)
def test_has_cardinal(text, expected):
    assert _has("HAS_CARDINAL", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This is the 2nd item.", True),
        ("The item is second.", False),
    ],
)
def test_has_ordinal(text, expected):
    assert _has("HAS_ORDINAL", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The rate is 15%.", True),
        ("The rate is fifteen.", False),
    ],
)
def test_has_percent(text, expected):
    assert _has("HAS_PERCENT", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The cost is $500.", True),
        ("The cost is five hundred dollars.", False),
    ],
)
def test_has_currency(text, expected):
    assert _has("HAS_CURRENCY", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The meeting is on 15 January 2024.", True),
        ("The meeting is on Monday.", False),
    ],
)
def test_has_date(text, expected):
    assert _has("HAS_DATE", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The briefing starts at 9:30am.", True),
        ("The briefing starts in the morning.", False),
    ],
)
def test_has_time(text, expected):
    assert _has("HAS_TIME", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("See https://example.gov.au for details.", True),
        ("See the website for details.", False),
    ],
)
def test_has_url(text, expected):
    assert _has("HAS_URL", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Contact us at info@example.gov.au.", True),
        ("Contact us at the office.", False),
    ],
)
def test_has_email(text, expected):
    assert _has("HAS_EMAIL", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("For example, i.e. these items.", True),
        ("For these items specifically.", False),
    ],
)
def test_has_abbreviation(text, expected):
    assert _has("HAS_ABBREVIATION", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The APS provides guidance.", True),
        ("The service provides guidance.", False),
    ],
)
def test_has_acronym(text, expected):
    assert _has("HAS_ACRONYM", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Section XI covers appeals.", True),
        ("Section eleven covers appeals.", False),
    ],
)
def test_has_roman_numeral(text, expected):
    assert _has("HAS_ROMAN_NUMERAL", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Plain language — it matters.", True),
        ("Plain language - it matters.", False),
    ],
)
def test_has_em_dash(text, expected):
    assert _has("HAS_EM_DASH", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Pages 10–20 are relevant.", True),
        ("Pages 10 to 20 are relevant.", False),
    ],
)
def test_has_en_dash(text, expected):
    assert _has("HAS_EN_DASH", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The well-known approach is used.", True),
        ("The approach is well known.", False),
    ],
)
def test_has_hyphen(text, expected):
    assert _has("HAS_HYPHEN", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The following applies: see below.", True),
        ("The following applies, see below.", False),
    ],
)
def test_has_colon(text, expected):
    assert _has("HAS_COLON", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("We considered two factors; both mattered.", True),
        ("We considered two factors and both mattered.", False),
    ],
)
def test_has_semicolon(text, expected):
    assert _has("HAS_SEMICOLON", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ('She said "hello" to them.', True),
        ("She greeted them.", False),
    ],
)
def test_has_straight_quote(text, expected):
    assert _has("HAS_STRAIGHT_QUOTE", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("She said “hello” to them.", True),
        ("She greeted them.", False),
    ],
)
def test_has_curly_quote(text, expected):
    assert _has("HAS_CURLY_QUOTE", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("There  are two spaces here.", True),
        ("There are single spaces here.", False),
    ],
)
def test_has_double_space(text, expected):
    assert _has("HAS_DOUBLE_SPACE", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The process (if applicable) applies.", True),
        ("The process applies if relevant.", False),
    ],
)
def test_has_parentheses(text, expected):
    assert _has("HAS_PARENTHESES", text) == expected
