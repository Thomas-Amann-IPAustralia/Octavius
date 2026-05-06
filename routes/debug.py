"""Debug route: GET /debug/explain

Registered only when ``OCTAVIUS_DEBUG_ENDPOINTS=1`` is set in the environment.
This is the "why didn't rule X fire?" diagnostic tool for Phase 4.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug")


@router.get("/explain")
def explain(
    text: str = Query(..., description="Document text to analyse"),
    rule_id: str | None = Query(None, description="Optional rule_id to trace"),
) -> dict:
    """Return extracted features, candidate rule_ids per segment, and an
    optional firing trace for a specific rule_id.

    Query parameters
    ----------------
    text:
        The document text to preprocess and analyse.
    rule_id:
        When provided, each segment entry gains a ``trace`` object showing
        whether the rule was in the candidate set and, if so, what findings
        it produced on the segment text.
    """
    from logic.features.extractor import extract
    from logic.preprocess import _get_nlp, preprocess
    import logic.indexed_dispatcher as _indexed

    doc = preprocess(text)
    nlp = _get_nlp()
    fs = extract(doc, nlp)

    segments_info = []
    for i, seg in enumerate(doc.segments):
        seg_features = fs.per_segment[i] | fs.document
        candidates = _indexed._compute_candidates(seg_features)

        trace = None
        if rule_id is not None:
            in_candidates = rule_id in candidates
            fired: list[dict] = []
            if in_candidates and rule_id in _indexed._RULE_BY_ID:
                rule = _indexed._RULE_BY_ID[rule_id]
                try:
                    raw = rule["check"](seg.text)
                    fired = [
                        {
                            "start_char": f["start_char"],
                            "end_char": f["end_char"],
                            "document_level": f["document_level"],
                            "ui_flag": f["ui_flag"],
                        }
                        for f in raw
                    ]
                except Exception as exc:
                    fired = [{"error": str(exc)}]

            all_of = list(_indexed._RULE_ALL_OF.get(rule_id, frozenset()))
            any_of = list(_indexed._RULE_ANY_OF.get(rule_id, frozenset()))
            none_of = list(_indexed._RULE_NONE_OF.get(rule_id, frozenset()))
            missing_all_of = [f for f in all_of if f not in seg_features]
            blocking_none_of = [f for f in none_of if f in seg_features]
            present_any_of = [f for f in any_of if f in seg_features]

            trace = {
                "in_candidates": in_candidates,
                "rule_all_of": sorted(all_of),
                "rule_any_of": sorted(any_of),
                "rule_none_of": sorted(none_of),
                "missing_all_of_features": sorted(missing_all_of),
                "blocking_none_of_features": sorted(blocking_none_of),
                "present_any_of_features": sorted(present_any_of),
                "fired_findings": fired,
            }

        segments_info.append({
            "kind": seg.kind,
            "offset": seg.offset,
            "lintable": seg.lintable,
            "text_preview": seg.text[:120],
            "features": sorted(seg_features),
            "candidate_count": len(candidates),
            "candidate_rule_ids": sorted(candidates),
            "trace": trace,
        })

    return {
        "document_features": sorted(fs.document),
        "has_structure": doc.has_structure,
        "sentence_count": doc.sentence_count,
        "segment_count": len(doc.segments),
        "segments": segments_info,
    }
