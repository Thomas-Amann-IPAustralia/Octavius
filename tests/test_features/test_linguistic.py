"""Tests for logic.features.linguistic — LING_* features."""

from __future__ import annotations

import pytest

from logic.features import linguistic
from logic.preprocess import Segment

@pytest.fixture(scope="module")
def nlp():
    import spacy
    return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])


def _seg(text: str, kind: str = "paragraph") -> Segment:
    return Segment(kind=kind, text=text, offset=0, lintable=True)


def _feats(nlp, text: str, kind: str = "paragraph", threshold: int = 25) -> frozenset[str]:
    return linguistic.extract(_seg(text, kind), nlp, threshold)


# ---------------------------------------------------------------------------
# LING_PASSIVE_VOICE
# ---------------------------------------------------------------------------


def test_passive_fires(nlp):
    feats = _feats(nlp, "The report was written by the manager.")
    assert "LING_PASSIVE_VOICE" in feats


def test_passive_not_active(nlp):
    feats = _feats(nlp, "The manager wrote the report.")
    assert "LING_PASSIVE_VOICE" not in feats


# ---------------------------------------------------------------------------
# LING_MODAL_VERB
# ---------------------------------------------------------------------------


def test_modal_fires(nlp):
    feats = _feats(nlp, "You should submit the form by Friday.")
    assert "LING_MODAL_VERB" in feats


def test_modal_not_present(nlp):
    feats = _feats(nlp, "Submit the form by Friday.")
    assert "LING_MODAL_VERB" not in feats


# ---------------------------------------------------------------------------
# LING_FIRST_PERSON
# ---------------------------------------------------------------------------


def test_first_person_fires_we(nlp):
    feats = _feats(nlp, "We consider the matter closed.")
    assert "LING_FIRST_PERSON" in feats


def test_first_person_fires_i(nlp):
    feats = _feats(nlp, "I reviewed the document carefully.")
    assert "LING_FIRST_PERSON" in feats


def test_first_person_absent(nlp):
    feats = _feats(nlp, "The team considers the matter closed.")
    assert "LING_FIRST_PERSON" not in feats


# ---------------------------------------------------------------------------
# LING_SECOND_PERSON
# ---------------------------------------------------------------------------


def test_second_person_fires(nlp):
    feats = _feats(nlp, "You should contact your manager.")
    assert "LING_SECOND_PERSON" in feats


def test_second_person_absent(nlp):
    feats = _feats(nlp, "Staff should contact their manager.")
    assert "LING_SECOND_PERSON" not in feats


# ---------------------------------------------------------------------------
# LING_IMPERATIVE
# ---------------------------------------------------------------------------


def test_imperative_fires(nlp):
    feats = _feats(nlp, "Submit the form before Friday.")
    assert "LING_IMPERATIVE" in feats


def test_imperative_not_declarative(nlp):
    feats = _feats(nlp, "The form must be submitted before Friday.")
    assert "LING_IMPERATIVE" not in feats


# ---------------------------------------------------------------------------
# LING_LONG_SENTENCE — threshold parameter test
# ---------------------------------------------------------------------------


_LONG_SENTENCE = (
    "The committee reviewed the documents and found that the proposed changes "
    "were consistent with current policy and required no further amendments."
)
# Count non-punct words
_LONG_WORD_COUNT = sum(
    1 for w in _LONG_SENTENCE.split() if w.strip(".,;:!?")
)


def test_long_sentence_fires_below_threshold(nlp):
    """Fires when threshold is below the actual word count."""
    feats = linguistic.extract(_seg(_LONG_SENTENCE), nlp, long_sentence_threshold=10)
    assert "LING_LONG_SENTENCE" in feats


def test_long_sentence_no_fire_above_threshold(nlp):
    """Does NOT fire when threshold exceeds the actual word count."""
    feats = linguistic.extract(_seg(_LONG_SENTENCE), nlp, long_sentence_threshold=50)
    assert "LING_LONG_SENTENCE" not in feats


# ---------------------------------------------------------------------------
# Non-lintable segment returns empty
# ---------------------------------------------------------------------------


def test_non_lintable_returns_empty(nlp):
    seg = Segment(kind="code_fence", text="some code", offset=0, lintable=False)
    assert linguistic.extract(seg, nlp, 25) == frozenset()


# ---------------------------------------------------------------------------
# nlp=None returns empty
# ---------------------------------------------------------------------------


def test_none_nlp_returns_empty():
    feats = linguistic.extract(_seg("The form was submitted."), None, 25)
    assert feats == frozenset()
