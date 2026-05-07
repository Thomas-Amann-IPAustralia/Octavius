"""Route: POST /check."""

from __future__ import annotations

import logging
import os
from typing import Any
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
    """Return the dispatcher module for the given env-flag value."""
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


class ZoneIn(BaseModel):
    kind: str
    text: str
    offset: int
    length: int
    ancestors: list[str] = []
    lintable: bool = True


class CheckRequest(BaseModel):
    text: str
    plain_text: str | None = None      # alias used by Tiptap frontend
    zones: list[ZoneIn] | None = None  # structural zones from the frontend
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

    effective_text = req.plain_text or req.text

    # When the frontend supplies structural zones, build the PreprocessedDoc
    # directly from them, bypassing markdown segmentation.
    _doc: Any = None
    if req.zones:
        from logic.preprocess import from_zones
        _doc = from_zones(
            effective_text,
            [z.model_dump() for z in req.zones],
        )

    # The legacy dispatcher does not support _doc; only the indexed one does.
    if _doc is not None and hasattr(dispatcher, "run_rules"):
        import inspect
        sig = inspect.signature(dispatcher.run_rules)
        if "_doc" in sig.parameters:
            findings = dispatcher.run_rules(
                effective_text,
                disabled_rule_ids=set(req.disabled_rule_ids) if req.disabled_rule_ids else None,
                disabled_taxonomies=set(req.disabled_taxonomies) if req.disabled_taxonomies else None,
                _doc=_doc,
            )
        else:
            findings = dispatcher.run_rules(
                effective_text,
                disabled_rule_ids=set(req.disabled_rule_ids) if req.disabled_rule_ids else None,
                disabled_taxonomies=set(req.disabled_taxonomies) if req.disabled_taxonomies else None,
            )
    else:
        findings = dispatcher.run_rules(
            effective_text,
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
            "start_char": f["start_char"],
            "end_char": f["end_char"],
            "severity": f["severity"],
            "document_level": f["document_level"],
            "mutation_class": f.get("mutation_class"),
            "grouped_rules": f.get("grouped_rules"),
            "suggestion": f.get("suggestion"),
        }
        for f in findings
    ]
