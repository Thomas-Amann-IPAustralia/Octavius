"""Cross-segment relational feature extractor (Phase 2).

Emits REL_* features that are defined by relationships between two or more
segments.  Receives the full :class:`~logic.preprocess.PreprocessedDoc`
because relations are cross-segment by definition.

Returns a ``list[frozenset[str]]`` parallel to ``doc.segments``.
"""

from __future__ import annotations

import re

from logic.preprocess import PreprocessedDoc, Segment

# ---------------------------------------------------------------------------
# REL_BULLET_AFTER_COLON
# ---------------------------------------------------------------------------

def _bullet_after_colon(
    segments: list[Segment],
    per_seg: list[set[str]],
) -> None:
    """Fire REL_BULLET_AFTER_COLON on list items whose predecessor ends with ':'."""
    # Only consider lintable segments in document order.
    lintable = [(i, s) for i, s in enumerate(segments) if s.lintable]
    for pos, (idx, seg) in enumerate(lintable):
        if seg.kind not in ("list_bullet", "list_numbered"):
            continue
        if pos == 0:
            continue
        _prev_idx, prev_seg = lintable[pos - 1]
        if prev_seg.text.rstrip().endswith(":"):
            per_seg[idx].add("REL_BULLET_AFTER_COLON")


# ---------------------------------------------------------------------------
# REL_ACRONYM_DEFINED_ON_FIRST_USE
# ---------------------------------------------------------------------------

# "Full Name (ACRO)" pattern: 1–6 initial-cap words followed by a parenthetical
# containing 2+ uppercase letters.
_ACRO_DEF_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z&,'-]+\s+){1,6}\(([A-Z]{2,})\)"
)
# Standalone acronym use: 2+ uppercase letters, word-bounded
_ACRO_USE_RE = re.compile(r"\b([A-Z]{2,})\b")


def _acronym_defined(
    segments: list[Segment],
    per_seg: list[set[str]],
) -> None:
    """Fire REL_ACRONYM_DEFINED_ON_FIRST_USE on segments that define an acronym.

    A segment fires when it contains the "Full Name (ACRO)" introduction pattern.
    The feature captures the quality of proper first-use definition; it does not
    cross-check every subsequent standalone use.
    """
    for i, seg in enumerate(segments):
        if _ACRO_DEF_RE.search(seg.text):
            per_seg[i].add("REL_ACRONYM_DEFINED_ON_FIRST_USE")


# ---------------------------------------------------------------------------
# REL_HEADING_FOLLOWED_BY_LIST
# ---------------------------------------------------------------------------

def _heading_followed_by_list(
    segments: list[Segment],
    per_seg: list[set[str]],
) -> None:
    """Fire REL_HEADING_FOLLOWED_BY_LIST on headings immediately followed by a list."""
    lintable = [(i, s) for i, s in enumerate(segments) if s.lintable]
    for pos, (idx, seg) in enumerate(lintable):
        if seg.kind != "heading":
            continue
        if pos + 1 >= len(lintable):
            continue
        _next_idx, next_seg = lintable[pos + 1]
        if next_seg.kind in ("list_bullet", "list_numbered"):
            per_seg[idx].add("REL_HEADING_FOLLOWED_BY_LIST")


# ---------------------------------------------------------------------------
# REL_CITATION_AFTER_QUOTE
# ---------------------------------------------------------------------------

# Citation-like pattern: parenthetical containing a 4-digit year
_CITATION_NEAR_RE = re.compile(r"\([^()]{2,80}\b\d{4}\b[^()]{0,20}\)")


def _citation_after_quote(
    doc: PreprocessedDoc,
    per_seg: list[set[str]],
) -> None:
    """Fire REL_CITATION_AFTER_QUOTE on segments where a citation follows a quote.

    Looks for a citation pattern within ~50 characters after any
    ``quoted_content`` mask region that falls inside the segment.
    """
    quote_regions = [
        (start, end)
        for start, end, _orig, kind in doc.mask_map
        if kind == "quoted_content"
    ]
    if not quote_regions:
        return

    for seg_idx, seg in enumerate(doc.segments):
        if not seg.lintable:
            continue
        seg_start = seg.offset
        seg_end = seg.offset + len(seg.text)

        for q_start, q_end in quote_regions:
            # Quote must lie entirely within this segment.
            if q_start < seg_start or q_end > seg_end:
                continue
            # Look in the ~50 chars immediately following the quote end.
            after_start = q_end - seg_start
            after_text = seg.text[after_start : after_start + 50]
            if _CITATION_NEAR_RE.search(after_text):
                per_seg[seg_idx].add("REL_CITATION_AFTER_QUOTE")
                break


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract(doc: PreprocessedDoc) -> list[frozenset[str]]:
    """Return per-segment relational features aligned to ``doc.segments``."""
    per_seg: list[set[str]] = [set() for _ in doc.segments]

    _bullet_after_colon(doc.segments, per_seg)
    _acronym_defined(doc.segments, per_seg)
    _heading_followed_by_list(doc.segments, per_seg)
    _citation_after_quote(doc, per_seg)

    return [frozenset(s) for s in per_seg]
