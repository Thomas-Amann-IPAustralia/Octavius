"""Octavius rules — passive voice plus all passing rules from rulebook.parquet."""

from __future__ import annotations

from typing import Any, List

from spacy.tokens import Doc

from logic.rulebook_loader import load_rulebook_rules


def check_passive_voice(doc: Doc) -> List[dict[str, Any]]:
    """Detect passive voice constructions via spaCy dependency parse.

    Looks for tokens with the ``auxpass`` dependency label (passive
    auxiliary) and returns a span covering the auxiliary through its
    head verb.
    """
    results: list[dict[str, Any]] = []
    seen_heads: set[int] = set()

    for token in doc:
        if token.dep_ == "auxpass" and token.head.i not in seen_heads:
            seen_heads.add(token.head.i)

            # Span from the passive auxiliary to (and including) the head verb
            start = min(token.i, token.head.i)
            end = max(token.i, token.head.i)
            span = doc[start : end + 1]

            results.append(
                {
                    "start_char": span.start_char,
                    "end_char": span.end_char,
                    "suggestion": f'Consider rewriting "{span.text}" in active voice.',
                }
            )

    return results


_PASSIVE_VOICE_RULE = {
    "id": "PASSIVE-VOICE-001",
    "title": "Passive voice detected",
    "message": "Passive voice can reduce clarity. Consider rewriting in active voice.",
    "severity": "warn",
    "category": "Grammar",
    "suggestion": None,
    "check": check_passive_voice,
}

RULES = [_PASSIVE_VOICE_RULE] + load_rulebook_rules()
