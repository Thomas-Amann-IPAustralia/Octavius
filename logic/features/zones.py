"""Zone and ancestor feature extractor (Phase 2).

Emits ZONE_* features from ``segment.kind`` and ANCESTOR_* features from
``segment.ancestors``.
"""

from __future__ import annotations

from logic.preprocess import Segment

_KIND_TO_ZONE: dict[str, str] = {
    "heading": "ZONE_HEADING",
    "paragraph": "ZONE_PARAGRAPH",
    "list_bullet": "ZONE_LIST_BULLET",
    "list_numbered": "ZONE_LIST_NUMBERED",
    "table_cell": "ZONE_TABLE_CELL",
    "blockquote": "ZONE_BLOCKQUOTE",
    "code_fence": "ZONE_CODE_FENCE",
    "inline_code": "ZONE_INLINE_CODE",
    "footnote": "ZONE_FOOTNOTE",
    "reference_list": "ZONE_REFERENCE_LIST",
}

# An ancestor value of "list_bullet" or "list_numbered" both map to
# ANCESTOR_LIST because the feature captures nesting inside any list kind.
_ANCESTOR_MAP: dict[str, str] = {
    "blockquote": "ANCESTOR_BLOCKQUOTE",
    "list_bullet": "ANCESTOR_LIST",
    "list_numbered": "ANCESTOR_LIST",
    "table": "ANCESTOR_TABLE",
    "footnote": "ANCESTOR_FOOTNOTE",
    "heading_section": "ANCESTOR_HEADING_SECTION",
}


def extract(segment: Segment) -> frozenset[str]:
    """Return zone and ancestor features for *segment*."""
    features: set[str] = set()

    zone = _KIND_TO_ZONE.get(segment.kind)
    if zone:
        features.add(zone)

    for ancestor in segment.ancestors:
        feat = _ANCESTOR_MAP.get(ancestor)
        if feat:
            features.add(feat)

    return frozenset(features)
