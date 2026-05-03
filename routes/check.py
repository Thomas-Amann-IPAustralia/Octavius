"""Route: POST /check."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

import logic.dispatcher as dispatcher

logger = logging.getLogger(__name__)

router = APIRouter()

_RULE_GROUPS_DEPRECATION_LOGGED = False


class CheckRequest(BaseModel):
    text: str
    disabled_rule_ids: list[str] | None = None
    disabled_taxonomies: list[str] | None = None
    # Legacy field — accepted but ignored.
    rule_groups: list[str] | None = None


@router.post("/check")
def check_text(req: CheckRequest) -> list[dict]:
    global _RULE_GROUPS_DEPRECATION_LOGGED
    if req.rule_groups is not None and not _RULE_GROUPS_DEPRECATION_LOGGED:
        logger.warning(
            "POST /check: 'rule_groups' is deprecated and ignored. "
            "Use 'disabled_rule_ids' and 'disabled_taxonomies' instead."
        )
        _RULE_GROUPS_DEPRECATION_LOGGED = True

    findings = dispatcher.run_rules(
        req.text,
        disabled_rule_ids=set(req.disabled_rule_ids) if req.disabled_rule_ids else None,
        disabled_taxonomies=set(req.disabled_taxonomies) if req.disabled_taxonomies else None,
    )

    return [
        {
            "rule_id": f["rule_id"],
            "group": f["taxonomy"],  # legacy compatibility
            "taxonomy": f["taxonomy"],
            "ui_flag": f["ui_flag"],
            "rule_summary": f["rule_summary"],
            "source_url": f["source_url"],
            "message": f["ui_flag"],  # legacy compatibility
            "start": f["start_char"],
            "end": f["end_char"],
            "severity": f["severity"],
            "document_level": f["document_level"],
        }
        for f in findings
    ]
