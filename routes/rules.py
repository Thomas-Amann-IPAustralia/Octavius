"""Routes: GET /rules and GET /taxonomies."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

import logic.dispatcher as dispatcher

router = APIRouter()


@router.get("/rules")
def get_rules() -> list[dict]:
    return [
        {
            "rule_id": r["rule_id"],
            "taxonomy": r["taxonomy"],
            "ui_flag": r["ui_flag"],
            "rule_summary": r["rule_summary"],
            "source_url": r["source_url"],
            "severity": r["severity"],
        }
        for r in dispatcher.get_rules()
    ]


@router.get("/taxonomies")
def get_taxonomies() -> list[dict]:
    counts: Counter[str] = Counter(r["taxonomy"] for r in dispatcher.get_rules())
    return [{"id": tax, "rule_count": counts[tax]} for tax in sorted(counts)]
