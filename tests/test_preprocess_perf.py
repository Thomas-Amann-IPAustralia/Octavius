"""Phase 1 preprocessing perf budget: 500-word document under 50 ms."""

from __future__ import annotations

import time

from logic.preprocess import preprocess


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


def test_preprocess_500_words_under_50ms():
    text = _build_500_word_doc()
    preprocess(text)  # warm caches (lazy spaCy load, regex compile)

    runs = 5
    elapsed = []
    for _ in range(runs):
        t0 = time.perf_counter()
        preprocess(text)
        elapsed.append(time.perf_counter() - t0)
    best = min(elapsed)
    assert best < 0.050, (
        f"preprocess took {best * 1000:.2f}ms; budget is 50 ms"
    )
