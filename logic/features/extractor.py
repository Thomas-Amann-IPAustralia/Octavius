"""Phase 2 feature extractor — orchestrator.

Maps a :class:`~logic.preprocess.PreprocessedDoc` to a :class:`FeatureSet`
by calling each sub-extractor in order, then validating every emitted name
against the frozen vocabulary.

Usage::

    import spacy
    from logic.preprocess import preprocess
    from logic.features.extractor import extract

    nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    doc = preprocess(some_text)
    fs = extract(doc, nlp)
    print(fs.document)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from logic.features import aps, document, exemptions, lexical, patterns, relations, zones
from logic.features.linguistic import extract_from_spacy_doc
from logic.features.vocabulary import validate_feature
from logic.preprocess import PreprocessedDoc


@dataclass(frozen=True)
class FeatureSet:
    """Immutable container for all features extracted from a single document.

    Attributes
    ----------
    document:
        Features that describe the document as a whole (DOC_*, EXEMPT_* that
        appear anywhere, and any per-segment feature promoted to document
        scope by the document extractor).
    per_segment:
        One ``frozenset[str]`` per element of ``doc.segments``, in the same
        order.
    """

    document: frozenset[str]
    per_segment: list[frozenset[str]]


def extract(
    doc: PreprocessedDoc,
    nlp: Any,
    long_sentence_threshold: int = 25,
) -> FeatureSet:
    """Extract all features from *doc* and return a validated :class:`FeatureSet`.

    Parameters
    ----------
    doc:
        Output of :func:`logic.preprocess.preprocess`.
    nlp:
        A loaded spaCy ``Language`` object (``en_core_web_sm`` with ner and
        lemmatizer disabled is the recommended pipeline).  Used by the
        linguistic sub-extractor to parse each lintable segment.  May be
        ``None`` to skip linguistic features entirely.
    long_sentence_threshold:
        Minimum non-punctuation word count in a sentence before
        ``LING_LONG_SENTENCE`` fires.  Defaults to 25.

    Raises
    ------
    ValueError
        If any sub-extractor emits a feature name not present in
        :data:`logic.features.vocabulary.FEATURE_VOCABULARY`.
    """
    n = len(doc.segments)
    per_seg: list[set[str]] = [set() for _ in range(n)]

    # --- Per-segment passes ---

    for i, seg in enumerate(doc.segments):
        per_seg[i].update(zones.extract(seg))

    for i, seg in enumerate(doc.segments):
        per_seg[i].update(lexical.extract(seg))

    # Linguistic features: batch all lintable segments through nlp.pipe() to
    # amortise the tok2vec cost rather than paying it once per segment.
    if nlp is not None:
        lintable_indices = [
            i for i, seg in enumerate(doc.segments)
            if seg.lintable and seg.text.strip()
        ]
        if lintable_indices:
            texts = [doc.segments[i].text for i in lintable_indices]
            for idx, spacy_doc in zip(lintable_indices, nlp.pipe(texts)):
                per_seg[idx].update(
                    extract_from_spacy_doc(spacy_doc, long_sentence_threshold)
                )

    for i, seg in enumerate(doc.segments):
        per_seg[i].update(patterns.extract(seg))

    # Relations extractor receives the full doc (cross-segment by nature)
    rel_features = relations.extract(doc)
    for i in range(min(n, len(rel_features))):
        per_seg[i].update(rel_features[i])

    for i, seg in enumerate(doc.segments):
        per_seg[i].update(aps.extract(seg))

    for i, seg in enumerate(doc.segments):
        per_seg[i].update(exemptions.extract_for_segment(seg, doc.mask_map))

    # --- Validate all per-segment features ---
    for i, seg_feats in enumerate(per_seg):
        for name in seg_feats:
            validate_feature(name)

    per_seg_frozen = [frozenset(s) for s in per_seg]

    # --- Document-level features ---
    doc_features: set[str] = set()
    doc_features.update(document.extract(doc.segments, per_seg_frozen, doc))
    doc_features.update(exemptions.extract_for_document(doc.mask_map))

    for name in doc_features:
        validate_feature(name)

    return FeatureSet(
        document=frozenset(doc_features),
        per_segment=per_seg_frozen,
    )
