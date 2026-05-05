"""Exemption feature extractor (Phase 2).

Maps ``mask_map`` exemption kinds to EXEMPT_* feature names.  Each unique
exemption kind that overlaps a segment's character range fires in that
segment's feature set.  The same kind anywhere in the document fires in the
document feature set.
"""

from __future__ import annotations

from logic.preprocess import Segment

_KIND_TO_EXEMPT: dict[str, str] = {
    "url": "EXEMPT_URL",
    "filepath": "EXEMPT_FILEPATH",
    "branchname": "EXEMPT_BRANCHNAME",
    "identifier": "EXEMPT_IDENTIFIER",
    "env_var": "EXEMPT_ENV_VAR",
    "product_name": "EXEMPT_PRODUCT_NAME",
    "mention_or_hashtag": "EXEMPT_MENTION_OR_HASHTAG",
    "code_snippet": "EXEMPT_CODE_SNIPPET",
    "quoted_content": "EXEMPT_QUOTED_CONTENT",
}


def extract_for_segment(
    segment: Segment,
    mask_map: list[tuple[int, int, str, str]],
) -> frozenset[str]:
    """Return EXEMPT_* features for mask entries that fall within *segment*."""
    features: set[str] = set()
    seg_start = segment.offset
    seg_end = segment.offset + len(segment.text)
    for start, end, _original, kind in mask_map:
        if start >= seg_start and end <= seg_end:
            feat = _KIND_TO_EXEMPT.get(kind)
            if feat:
                features.add(feat)
    return frozenset(features)


def extract_for_document(
    mask_map: list[tuple[int, int, str, str]],
) -> frozenset[str]:
    """Return EXEMPT_* features for every distinct exemption kind in *mask_map*."""
    features: set[str] = set()
    for _start, _end, _original, kind in mask_map:
        feat = _KIND_TO_EXEMPT.get(kind)
        if feat:
            features.add(feat)
    return frozenset(features)
