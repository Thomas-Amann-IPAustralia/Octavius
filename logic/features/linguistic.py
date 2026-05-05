"""Linguistic feature extractor (Phase 2).

Emits LING_* features using spaCy dependency and POS tags.

The primary entry point used by the orchestrator is ``extract_from_spacy_doc``
which operates on a pre-built spaCy ``Doc``.  The orchestrator batches all
lintable segment texts through ``nlp.pipe()`` before calling this function,
amortising the tok2vec cost across all segments.

The convenience ``extract(segment, nlp, threshold)`` function is provided for
direct per-segment use in tests.

``long_sentence_threshold`` is the canonical threshold parameter: it controls
when LING_LONG_SENTENCE fires and lives here rather than in the feature name.
"""

from __future__ import annotations

from typing import Any

from logic.preprocess import Segment

_FIRST_PERSON_LEMMAS: frozenset[str] = frozenset(
    {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
)
_SECOND_PERSON_LEMMAS: frozenset[str] = frozenset(
    {"you", "your", "yours", "yourself", "yourselves"}
)


def extract_from_spacy_doc(spacy_doc: Any, long_sentence_threshold: int) -> frozenset[str]:
    """Return linguistic features from an already-parsed spaCy ``Doc`` object.

    Used by the orchestrator after batch-processing segments via
    ``nlp.pipe()``.  The full parsing cost is paid once per batch rather
    than once per segment.
    """
    features: set[str] = set()

    for token in spacy_doc:
        # Passive voice: nsubjpass or auxpass dependency
        if token.dep_ in ("nsubjpass", "auxpass"):
            features.add("LING_PASSIVE_VOICE")

        # Modal verb: tag MD (can, could, may, might, must, shall, should, will, would)
        if token.tag_ == "MD":
            features.add("LING_MODAL_VERB")

        # First-person pronoun by lemma
        if token.lemma_.lower() in _FIRST_PERSON_LEMMAS:
            features.add("LING_FIRST_PERSON")

        # Second-person pronoun by lemma
        if token.lemma_.lower() in _SECOND_PERSON_LEMMAS:
            features.add("LING_SECOND_PERSON")

        # Proper noun (PROPN POS)
        if token.pos_ == "PROPN":
            features.add("LING_PROPER_NOUN")

        # All-caps alphabetic token longer than one character
        if token.is_alpha and token.text.isupper() and len(token.text) > 1:
            features.add("LING_ALL_CAPS_TOKEN")

        # Negation: neg dependency arc
        if token.dep_ == "neg":
            features.add("LING_NEGATION")

    # Title-case sequence: 2+ consecutive non-punctuation tokens each starting
    # with an uppercase letter followed by lowercase letters.
    run = 0
    for token in spacy_doc:
        if token.is_punct or token.is_space:
            run = 0
            continue
        text = token.text
        if text and text[0].isupper() and (len(text) == 1 or text[1:].islower()):
            run += 1
            if run >= 2:
                features.add("LING_TITLE_CASE_SEQUENCE")
        else:
            run = 0

    # Imperative: a sentence whose ROOT token is a bare infinitive (VB) with
    # no nsubj dependent.  We do not require it to be the first token so that
    # headings with a leading '#' marker still fire correctly.
    for sent in spacy_doc.sents:
        has_root_vb = any(t.dep_ == "ROOT" and t.tag_ == "VB" for t in sent)
        has_nsubj = any(t.dep_ in ("nsubj", "nsubjpass") for t in sent)
        if has_root_vb and not has_nsubj:
            features.add("LING_IMPERATIVE")

    # Long sentence: any sentence whose non-punctuation word count meets the
    # threshold.  Threshold lives on the extractor parameter, not the name.
    for sent in spacy_doc.sents:
        word_count = sum(1 for t in sent if not t.is_punct and not t.is_space)
        if word_count >= long_sentence_threshold:
            features.add("LING_LONG_SENTENCE")
            break

    return frozenset(features)


def extract(
    segment: Segment,
    nlp: Any,
    long_sentence_threshold: int,
) -> frozenset[str]:
    """Return linguistic features for *segment* (convenience wrapper for tests).

    For production use the orchestrator calls ``extract_from_spacy_doc``
    directly after batching via ``nlp.pipe()``.

    Returns an empty frozenset for non-lintable segments or when *nlp* is
    ``None``.
    """
    if not segment.lintable or nlp is None or not segment.text.strip():
        return frozenset()
    return extract_from_spacy_doc(nlp(segment.text), long_sentence_threshold)
