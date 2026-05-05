"""Phase 2 feature extraction perf budget: 500-word document under 100 ms.

The budget covers the full extract() call on a pre-built PreprocessedDoc
(preprocessing time is measured separately in test_preprocess_perf.py).
The warm minimum of 5 runs must stay under 100 ms.
"""

from __future__ import annotations

import time

import pytest

from logic.features.extractor import extract
from logic.preprocess import preprocess


@pytest.fixture(scope="module")
def nlp():
    import spacy
    return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])


def _build_500_word_doc() -> str:
    paragraph = (
        "The quick brown fox jumps over the lazy dog. "
        "Plain language guidance helps the public service write clearly. "
        "Use https://example.gov.au to find more information about Render. "
        "Avoid env vars like PATH and DEBUG_MODE in user-facing copy. "
        "Refer to feature/onboarding-flow when reviewing the main branch. "
    )
    words_per = len(paragraph.split())
    repeats = (500 // words_per) + 1
    sections = []
    for i in range(repeats):
        sections.append(f"## Section {i + 1}\n\n{paragraph}\n")
    text = "\n".join(sections)
    assert len(text.split()) >= 500
    return text


def test_feature_extraction_500_words_under_100ms(nlp):
    text = _build_500_word_doc()
    doc = preprocess(text)

    # Warm: ensure spaCy model and any lazy lists are loaded
    extract(doc, nlp)

    runs = 5
    elapsed = []
    for _ in range(runs):
        t0 = time.perf_counter()
        extract(doc, nlp)
        elapsed.append(time.perf_counter() - t0)

    best = min(elapsed)
    assert best < 0.100, (
        f"feature extraction took {best * 1000:.2f}ms; budget is 100 ms"
    )
