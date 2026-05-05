"""Shared types for the compiled rulebook engine."""

from __future__ import annotations

from typing import Callable, Literal, NotRequired, TypedDict


MutationClass = Literal["safe_replace", "requires_rewrite", "human_review"]


class FeatureRequirements(TypedDict):
    all_of: list[str]
    any_of: list[str]
    none_of: list[str]


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
    # Phase 4 will populate these; default ``None`` until then.
    grouped_rules: NotRequired[list[str] | None]
    mutation_class: NotRequired[MutationClass | None]


class CompiledRule(TypedDict):
    rule_id: str
    taxonomy: Literal["regex", "lookup", "structural"]
    ui_flag: str
    rule_summary: str
    source_url: str
    severity: str
    check: Callable[[str], list[Finding]]
    # Phase 3 populates these; default ``None`` until then.
    required_features: NotRequired[dict[str, list[str]] | None]
    mutation_class: NotRequired[MutationClass | None]
