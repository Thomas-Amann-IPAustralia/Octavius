"""APS domain feature extractor (Phase 2).

Emits APS_* features by matching segment text against:
- Regex patterns for legislation references and long-form dates
- Word lists loaded from ``logic/features/data/`` for department names,
  ministerial titles, and Commonwealth entities

Word lists start sparse; expand them as Phase 3's batch surfaces gaps.
"""

from __future__ import annotations

import re
from pathlib import Path

from logic.preprocess import Segment

_DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Legislation: "Name Act YYYY", "Name Regulations YYYY", etc.
# Deliberately broad to catch novel act names not in any wordlist.
_LEGISLATION_RE = re.compile(
    r"\b[A-Z][A-Za-z ,\(\)&'\-]{2,60}?"
    r"\s+(?:Act|Code|Regulation|Regulations|Rules|Order|Ordinance"
    r"|Determination|Proclamation|Declaration)\s+\d{4}\b"
)

# Date in long form: "1 January 2024", "25 December 1999"
_DATE_LONGFORM_RE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July"
    r"|August|September|October|November|December)\s+\d{4}\b",
    re.IGNORECASE,
)

# Department: "Department of X" pattern covers most cases; wordlist supplements.
_DEPT_PATTERN_RE = re.compile(r"\bDepartment\s+of\s+(?:the\s+)?[A-Z][A-Za-z ,&'\-]+")

# ---------------------------------------------------------------------------
# Lazy-loaded wordlists
# ---------------------------------------------------------------------------

_dept_wordlist: frozenset[str] = frozenset()
_ministerial_titles: frozenset[str] = frozenset()
_commonwealth_entities: frozenset[str] = frozenset()
_lists_loaded = False


def _load_list(filename: str) -> frozenset[str]:
    path = _DATA_DIR / filename
    if not path.exists():
        return frozenset()
    return frozenset(
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def _ensure_loaded() -> None:
    global _dept_wordlist, _ministerial_titles, _commonwealth_entities, _lists_loaded
    if _lists_loaded:
        return
    _dept_wordlist = _load_list("department_names.txt")
    _ministerial_titles = _load_list("ministerial_titles.txt")
    _commonwealth_entities = _load_list("commonwealth_entities.txt")
    _lists_loaded = True


def _reload() -> None:
    """Force reload of wordlists (for testing)."""
    global _lists_loaded
    _lists_loaded = False
    _ensure_loaded()


def extract(segment: Segment) -> frozenset[str]:
    """Return APS domain features for *segment*."""
    _ensure_loaded()
    features: set[str] = set()
    text = segment.text
    text_lower = text.lower()

    # Legislation reference
    if _LEGISLATION_RE.search(text):
        features.add("APS_LEGISLATION_REFERENCE")

    # Department name: pattern match or wordlist membership
    if _DEPT_PATTERN_RE.search(text):
        features.add("APS_DEPARTMENT_NAME")
    else:
        for dept in _dept_wordlist:
            if dept in text_lower:
                features.add("APS_DEPARTMENT_NAME")
                break

    # Ministerial title: substring match against the lowercased text
    for title in _ministerial_titles:
        if title in text_lower:
            features.add("APS_MINISTERIAL_TITLE")
            break

    # Long-form date
    if _DATE_LONGFORM_RE.search(text):
        features.add("APS_DATE_LONGFORM")

    # Commonwealth entity: substring match (case-insensitive)
    for entity in _commonwealth_entities:
        if entity in text_lower:
            features.add("APS_COMMONWEALTH_ENTITY")
            break

    return frozenset(features)
