"""Document-scope feature extractor (Phase 2).

Emits DOC_* features that summarise the whole document.  Called after all
per-segment features have been assembled so it can inspect the full
per-segment feature matrix.
"""

from __future__ import annotations

from logic.preprocess import PreprocessedDoc, Segment

# Citation-bearing features: if any segment carries either of these, the
# document has citations.
_CITATION_FEATURES: frozenset[str] = frozenset(
    {"APS_LEGISLATION_REFERENCE", "PATTERN_CITATION_PARENS"}
)


def extract(
    segments: list[Segment],
    per_segment_features: list[frozenset[str]],
    doc: PreprocessedDoc,
) -> frozenset[str]:
    """Return document-level features.

    Parameters
    ----------
    segments:
        ``doc.segments`` (the same list passed to all sub-extractors).
    per_segment_features:
        Accumulated per-segment feature sets at the time this is called.
        Must be parallel to *segments*.
    doc:
        The full :class:`~logic.preprocess.PreprocessedDoc`.
    """
    features: set[str] = set()

    # Structural presence flags
    if any(s.kind == "heading" for s in segments):
        features.add("DOC_HAS_HEADINGS")

    if any(s.kind in ("list_bullet", "list_numbered") for s in segments):
        features.add("DOC_HAS_LISTS")

    # Citation presence: any segment that carries a citation feature
    if any(_CITATION_FEATURES & seg_feats for seg_feats in per_segment_features):
        features.add("DOC_HAS_CITATIONS")

    # Language
    if doc.language == "en":
        features.add("DOC_LANGUAGE_EN")

    return frozenset(features)
