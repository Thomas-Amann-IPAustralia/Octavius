"""Shared types for the compiled rulebook engine."""

from __future__ import annotations

from typing import Callable, Literal, TypedDict


class Finding(TypedDict):
    start_char: int
    end_char: int
    rule_id: str
    taxonomy: str
    ui_flag: str
    rule_summary: str
    source_url: str
    severity: str
    document_level: bool


class CompiledRule(TypedDict):
    rule_id: str
    taxonomy: Literal["regex", "lookup", "structural"]
    ui_flag: str
    rule_summary: str
    source_url: str
    severity: str
    check: Callable[[str], list[Finding]]
