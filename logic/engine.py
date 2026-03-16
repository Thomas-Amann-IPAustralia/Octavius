"""Octavius linting engine — minimal vertical slice."""

from __future__ import annotations

from typing import Any, Callable, List, TypedDict

import spacy
from spacy.tokens import Doc


class Finding(TypedDict):
    start_char: int
    end_char: int
    rule_id: str
    message: str
    severity: str
    suggestion: str | None


class Rule(TypedDict):
    id: str
    title: str
    message: str
    severity: str
    suggestion: str | None
    check: Callable[[Doc], List[dict[str, Any]]]


# Load spaCy model once at module level
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None


def get_spacy_status() -> bool:
    """Return True if the spaCy model loaded successfully."""
    return nlp is not None


def lint_text(text: str, rules: list[Rule]) -> list[Finding]:
    """Run every rule against *text* and return sorted findings."""
    if not nlp:
        return [
            Finding(
                start_char=0,
                end_char=0,
                rule_id="SYSTEM-SPACY-NOT-LOADED",
                message="spaCy language model not loaded.",
                severity="error",
                suggestion="Run: python -m spacy download en_core_web_sm",
            )
        ]

    doc = nlp(text)
    findings: list[Finding] = []

    for rule in rules:
        hits = rule["check"](doc)
        for hit in hits:
            findings.append(
                Finding(
                    start_char=hit["start_char"],
                    end_char=hit["end_char"],
                    rule_id=rule["id"],
                    message=rule["message"],
                    severity=rule["severity"],
                    suggestion=hit.get("suggestion") or rule.get("suggestion"),
                )
            )

    findings.sort(key=lambda f: f["start_char"])
    return findings
