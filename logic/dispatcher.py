"""Rule dispatcher — load once at import time, then serve requests.

Usage
-----
    from logic.dispatcher import run_rules

    findings = run_rules(text, disabled_taxonomies={"structural"})
"""

from __future__ import annotations

import logging

from logic.rulebook.loader import load_rules
from logic.rulebook.types import CompiledRule, Finding

logger = logging.getLogger(__name__)

# Compiled rule list — populated once when this module is first imported.
_RULES: list[CompiledRule] = load_rules()


def run_rules(
    text: str,
    disabled_rule_ids: set[str] | None = None,
    disabled_taxonomies: set[str] | None = None,
) -> list[Finding]:
    """Run all enabled rules against *text* and return sorted findings.

    Parameters
    ----------
    text:
        The document text to analyse.
    disabled_rule_ids:
        Rule IDs to skip (exact match on ``rule_id``).
    disabled_taxonomies:
        Taxonomy names to skip entirely (e.g. ``{"structural"}``).

    Returns
    -------
    list[Finding]
        All findings, sorted by ``(start_char, rule_id)``.  Single-rule
        failures are caught and logged; they never propagate to the caller.
    """
    skip_ids = disabled_rule_ids or set()
    skip_taxs = disabled_taxonomies or set()

    findings: list[Finding] = []

    for rule in _RULES:
        if rule["rule_id"] in skip_ids:
            continue
        if rule["taxonomy"] in skip_taxs:
            continue

        try:
            findings.extend(rule["check"](text))
        except Exception:
            logger.exception("Rule %s raised during execution — skipping", rule["rule_id"])

    findings.sort(key=lambda f: (f["start_char"], f["rule_id"]))
    return findings


def get_rules() -> list[CompiledRule]:
    """Return the cached compiled rule list (read-only reference)."""
    return _RULES
