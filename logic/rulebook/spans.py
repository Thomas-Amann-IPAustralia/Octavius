"""Offset-recovery helpers for the rulebook engine."""

from __future__ import annotations

import re


def find_term_spans(text: str, term: str) -> list[tuple[int, int]]:
    """Return all (start, end) char offsets of *term* in *text*.

    Uses word-boundary anchors so 'the' does not match inside 'there'.
    Case-insensitive.
    """
    pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    return [(m.start(), m.end()) for m in pattern.finditer(text)]
