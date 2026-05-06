"""Route: POST /check."""

from __future__ import annotations

import logging
import os
from types import ModuleType

import logic.dispatcher as _legacy_dispatcher
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

_RULE_GROUPS_DEPRECATION_LOGGED = False

# ---------------------------------------------------------------------------
# OCTAVIUS_DISPATCHER env-flag plumbing
# ---------------------------------------------------------------------------

_VALID_DISPATCHERS = ("legacy", "indexed")


def _resolve_dispatcher(name: str | None) -> ModuleType:
    """Return the dispatcher module for the given env-flag value.

    ``legacy`` → ``logic.dispatcher`` (default).
    ``indexed`` → ``logic.indexed_dispatcher`` (Phase 4+).
    Unknown values fall back to ``legacy`` with a warning.
    """
    choice = (name or "legacy").strip().lower()
    if choice not in _VALID_DISPATCHERS:
        logger.warning(
            "OCTAVIUS_DISPATCHER=%r is not recognised; falling back to 'legacy'. "
            "Valid values: %s",
            name,
            _VALID_DISPATCHERS,
        )
        choice = "legacy"

    if choice == "indexed":
        import logic.indexed_dispatcher as _indexed_dispatcher
        return _indexed_dispatcher

    return _legacy_dispatcher


dispatcher = _resolve_dispatcher(os.environ.get("OCTAVIUS_DISPATCHER"))


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
            "mutation_class": f.get("mutation_class"),
            "grouped_rules": f.get("grouped_rules"),
        }
        for f in findings
    ]
