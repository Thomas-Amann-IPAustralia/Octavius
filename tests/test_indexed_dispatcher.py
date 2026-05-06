"""Tests for the Phase 4 inverted-index dispatcher.

Covers:
- Integration smoke tests against real rulebook
- Unit tests of the candidate-selection algorithm (using synthetic rules)
- Post-firing logic: budget, dedup, grouping, document-level gating
- Mutation-class propagation
- Legacy parity baseline (Jaccard, no threshold asserted)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Callable

import pytest

import logic.indexed_dispatcher as idx
from logic.indexed_dispatcher import (
    _FIRING_BUDGET,
    _apply_firing_budget,
    _compute_candidates,
    _dedup_spanned,
    _group_by_span,
    _most_conservative,
    run_rules,
)
from logic.rulebook.types import CompiledRule, Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    start: int,
    end: int,
    rule_id: str,
    mutation_class=None,
    document_level: bool = False,
    **kwargs,
) -> Finding:
    return Finding(
        start_char=start,
        end_char=end,
        rule_id=rule_id,
        taxonomy=kwargs.get("taxonomy", "regex"),
        ui_flag=kwargs.get("ui_flag", f"flag:{rule_id}"),
        rule_summary=kwargs.get("rule_summary", f"Rule {rule_id}"),
        source_url=kwargs.get("source_url", "https://example.com"),
        severity=kwargs.get("severity", "warning"),
        document_level=document_level,
        grouped_rules=None,
        mutation_class=mutation_class,
    )


def _make_compiled_rule(
    rule_id: str,
    pattern: str,
    mutation_class=None,
    required_features: dict | None = None,
) -> CompiledRule:
    compiled = re.compile(pattern, re.IGNORECASE)

    def check(text: str) -> list[Finding]:
        return [
            _make_finding(m.start(), m.end(), rule_id, mutation_class=mutation_class)
            for m in compiled.finditer(text)
        ]

    return CompiledRule(
        rule_id=rule_id,
        taxonomy="regex",
        ui_flag=f"flag:{rule_id}",
        rule_summary=f"Rule {rule_id}",
        source_url="https://example.com",
        severity="warning",
        check=check,
        required_features=required_features,
        mutation_class=mutation_class,
    )


# ---------------------------------------------------------------------------
# The Step 1 noisy example
# ---------------------------------------------------------------------------

_STEP_1_TEXT = (
    "Step 1 — Merge this branch to main\n"
    "The changes just pushed need to be on main before Render deploys them."
)


def test_step_1_example_quiet():
    """Indexed dispatcher should produce ≤6 findings for the noisy example."""
    findings = run_rules(_STEP_1_TEXT)
    assert isinstance(findings, list)
    assert len(findings) <= 6, (
        f"Expected ≤6 findings, got {len(findings)}: "
        + ", ".join(f['rule_id'] for f in findings)
    )


# ---------------------------------------------------------------------------
# Unconstrained rules
# ---------------------------------------------------------------------------

_SMOKE_TEXT = """\
Use the Australian Government Style Manual (Style Manual) when writing.
Arrange the works alphabetically by author name.
The policy improved service delivery (Smith, 2020).

References
Smith, J. (2020). Policy change in practice. Australian Government Press.
"""


def test_unconstrained_rules_still_run():
    """Rules with required_features=None must still fire on matching input."""
    findings = run_rules(_SMOKE_TEXT)
    assert isinstance(findings, list)
    assert len(findings) >= 1, "Expected at least one finding from unconstrained rules"


# ---------------------------------------------------------------------------
# Candidate-set algorithm — synthetic-rule unit tests
# ---------------------------------------------------------------------------

def _inject_synthetic_rule(
    monkeypatch,
    rule_id: str,
    all_of: list[str],
    any_of: list[str],
    none_of: list[str],
) -> None:
    """Temporarily add a synthetic constrained rule to the module index."""
    new_rule_all_of = dict(idx._RULE_ALL_OF) | {rule_id: frozenset(all_of)}
    new_rule_any_of = dict(idx._RULE_ANY_OF) | {rule_id: frozenset(any_of)}
    new_rule_none_of = dict(idx._RULE_NONE_OF) | {rule_id: frozenset(none_of)}
    new_constrained = list(idx._CONSTRAINED_IDS) + [rule_id]

    monkeypatch.setattr(idx, "_RULE_ALL_OF", new_rule_all_of)
    monkeypatch.setattr(idx, "_RULE_ANY_OF", new_rule_any_of)
    monkeypatch.setattr(idx, "_RULE_NONE_OF", new_rule_none_of)
    monkeypatch.setattr(idx, "_CONSTRAINED_IDS", new_constrained)


def test_none_of_blocks_retrieval(monkeypatch):
    """Rule with none_of=[EXEMPT_BRANCHNAME] must not retrieve when the feature
    is present (e.g. segment containing masked 'main')."""
    rule_id = "SYNTH_NONE_OF_TEST"
    _inject_synthetic_rule(monkeypatch, rule_id, [], [], ["EXEMPT_BRANCHNAME"])

    # Feature set that includes EXEMPT_BRANCHNAME (text containing "main")
    features_with_exempt = frozenset({"EXEMPT_BRANCHNAME", "ZONE_PARAGRAPH"})
    candidates = _compute_candidates(features_with_exempt)
    assert rule_id not in candidates

    # Without EXEMPT_BRANCHNAME the rule IS retrieved
    features_without = frozenset({"ZONE_PARAGRAPH"})
    candidates_2 = _compute_candidates(features_without)
    assert rule_id in candidates_2


def test_all_of_strict(monkeypatch):
    """Rule with all_of=[LING_PASSIVE_VOICE, HAS_CARDINAL] retrieves only
    when both features are present."""
    rule_id = "SYNTH_ALL_OF_TEST"
    _inject_synthetic_rule(
        monkeypatch, rule_id, ["LING_PASSIVE_VOICE", "HAS_CARDINAL"], [], []
    )

    # Both present → retrieved
    both = frozenset({"LING_PASSIVE_VOICE", "HAS_CARDINAL", "ZONE_PARAGRAPH"})
    assert rule_id in _compute_candidates(both)

    # Only one present → NOT retrieved
    one_only = frozenset({"LING_PASSIVE_VOICE", "ZONE_PARAGRAPH"})
    assert rule_id not in _compute_candidates(one_only)

    # Neither present → NOT retrieved
    neither = frozenset({"ZONE_PARAGRAPH"})
    assert rule_id not in _compute_candidates(neither)


def test_any_of_loose(monkeypatch):
    """Rule with any_of=[ZONE_PARAGRAPH, ZONE_LIST_BULLET] retrieves when
    either feature is present."""
    rule_id = "SYNTH_ANY_OF_TEST"
    _inject_synthetic_rule(
        monkeypatch, rule_id, [], ["ZONE_PARAGRAPH", "ZONE_LIST_BULLET"], []
    )

    # ZONE_PARAGRAPH present → retrieved
    para_features = frozenset({"ZONE_PARAGRAPH"})
    assert rule_id in _compute_candidates(para_features)

    # ZONE_LIST_BULLET present → retrieved
    list_features = frozenset({"ZONE_LIST_BULLET"})
    assert rule_id in _compute_candidates(list_features)

    # Neither present → NOT retrieved
    heading_only = frozenset({"ZONE_HEADING"})
    assert rule_id not in _compute_candidates(heading_only)


def test_exempt_in_all_of_rejected_at_load(monkeypatch, caplog):
    """A rule with EXEMPT_URL in all_of must be logged as an error and
    excluded from the constrained index (never fires)."""
    bad_rule_id = "SYNTH_EXEMPT_IN_ALL_OF"
    bad_rule = _make_compiled_rule(
        bad_rule_id,
        r"bad",
        required_features={"all_of": ["EXEMPT_URL"], "any_of": [], "none_of": []},
    )

    # Replace module state with fresh containers + our bad rule only
    monkeypatch.setattr(idx, "_RULES", [bad_rule])
    monkeypatch.setattr(idx, "_RULE_ALL_OF", {})
    monkeypatch.setattr(idx, "_RULE_ANY_OF", {})
    monkeypatch.setattr(idx, "_RULE_NONE_OF", {})
    monkeypatch.setattr(idx, "_CONSTRAINED_IDS", [])
    monkeypatch.setattr(idx, "_INDEX_ALL_OF", {})
    monkeypatch.setattr(idx, "_INDEX_ANY_OF", {})
    monkeypatch.setattr(idx, "_INDEX_NONE_OF", {})

    with caplog.at_level(logging.ERROR, logger="logic.indexed_dispatcher"):
        unconstrained = idx._build_index()

    # Bad rule must be absent from both the constrained index and unconstrained set
    assert bad_rule_id not in idx._CONSTRAINED_IDS
    assert bad_rule_id not in unconstrained
    # Error must have been logged
    assert any(
        "EXEMPT" in rec.message or "EXEMPT_URL" in rec.message
        for rec in caplog.records
    ), f"Expected EXEMPT error logged; got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Mutation-class propagation
# ---------------------------------------------------------------------------

def test_mutation_class_propagated(monkeypatch):
    """A fired finding must carry mutation_class from its rule."""
    rule_id = "SYNTH_MC_RULE"
    synth_rule = _make_compiled_rule(
        rule_id, r"\bpassive\b", mutation_class="requires_rewrite"
    )

    # Inject into module state so the dispatcher can find it
    new_rule_by_id = dict(idx._RULE_BY_ID) | {rule_id: synth_rule}
    new_unconstrained = frozenset(idx._UNCONSTRAINED | {rule_id})
    monkeypatch.setattr(idx, "_RULE_BY_ID", new_rule_by_id)
    monkeypatch.setattr(idx, "_UNCONSTRAINED", new_unconstrained)

    findings = run_rules("The form was submitted in a passive voice way.")
    matched = [f for f in findings if f["rule_id"] == rule_id]
    assert matched, f"Expected rule {rule_id} to fire"
    assert matched[0]["mutation_class"] == "requires_rewrite"


def test_grouped_finding_takes_most_conservative_mutation():
    """Two rules on the same span → grouped Finding with most conservative class."""
    f1 = _make_finding(0, 5, "rule-a", mutation_class="safe_replace")
    f2 = _make_finding(0, 5, "rule-b", mutation_class="human_review")

    grouped = _group_by_span([f1, f2])
    assert len(grouped) == 1
    assert grouped[0]["mutation_class"] == "human_review"
    assert grouped[0]["grouped_rules"] is not None
    assert set(grouped[0]["grouped_rules"]) == {"rule-a", "rule-b"}


def test_most_conservative_ordering():
    """Conservatism order: human_review > requires_rewrite > safe_replace > None."""
    assert _most_conservative(["safe_replace", "human_review"]) == "human_review"
    assert _most_conservative(["safe_replace", "requires_rewrite"]) == "requires_rewrite"
    assert _most_conservative(["requires_rewrite", "human_review"]) == "human_review"
    assert _most_conservative([None, "safe_replace"]) == "safe_replace"
    assert _most_conservative([None, None]) is None


# ---------------------------------------------------------------------------
# Firing budget
# ---------------------------------------------------------------------------

def test_firing_budget_summary():
    """A rule that fires 10 times → 5 spanned findings + 1 budget summary."""
    rule_id = "rule-budget-test"
    findings = [_make_finding(i * 10, i * 10 + 5, rule_id) for i in range(10)]

    kept, summaries = _apply_firing_budget(findings)

    assert len(kept) == _FIRING_BUDGET
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["rule_id"] == rule_id
    assert summary["document_level"] is True
    assert "10" in summary["ui_flag"]
    assert summary["grouped_rules"] == [rule_id]


def test_firing_budget_not_triggered_at_limit():
    """Exactly _FIRING_BUDGET findings → no summary produced."""
    rule_id = "rule-at-limit"
    findings = [_make_finding(i * 10, i * 10 + 5, rule_id) for i in range(_FIRING_BUDGET)]
    kept, summaries = _apply_firing_budget(findings)
    assert len(kept) == _FIRING_BUDGET
    assert summaries == []


# ---------------------------------------------------------------------------
# Span deduplication and grouping
# ---------------------------------------------------------------------------

def test_span_grouping():
    """Two rules on the same span → one Finding with grouped_rules length 2."""
    f1 = _make_finding(0, 5, "rule-x")
    f2 = _make_finding(0, 5, "rule-y")

    grouped = _group_by_span([f1, f2])
    assert len(grouped) == 1
    assert grouped[0]["grouped_rules"] is not None
    assert len(grouped[0]["grouped_rules"]) == 2
    assert set(grouped[0]["grouped_rules"]) == {"rule-x", "rule-y"}


def test_dedup_exact_span_rule():
    """Exact (start, end, rule_id) duplicates collapse to one Finding."""
    f1 = _make_finding(0, 5, "rule-z")
    f2 = _make_finding(0, 5, "rule-z")  # identical

    deduped = _dedup_spanned([f1, f2])
    assert len(deduped) == 1


def test_different_spans_not_grouped():
    """Findings at different positions are not grouped."""
    f1 = _make_finding(0, 5, "rule-a")
    f2 = _make_finding(10, 15, "rule-b")

    grouped = _group_by_span([f1, f2])
    assert len(grouped) == 2


# ---------------------------------------------------------------------------
# Document-level gating
# ---------------------------------------------------------------------------

def test_document_level_gating_short_input():
    """Single-sentence input with no structure must not emit document-level
    findings (other than budget summaries, which have grouped_rules set)."""
    text = "The policy improved service delivery."
    findings = run_rules(text)

    # Non-budget document-level findings have grouped_rules=None
    real_doc_level = [
        f for f in findings
        if f["document_level"] and f.get("grouped_rules") is None
    ]
    assert real_doc_level == [], (
        f"Expected no document-level findings for short input; got "
        + ", ".join(f["rule_id"] for f in real_doc_level)
    )


def test_document_level_gating_rich_input():
    """A document with headings and ≥3 sentences may emit document-level
    findings if rules produce them."""
    text = """\
# Introduction

This document discusses policy delivery standards.
Departments must follow these guidelines when drafting materials.
The review committee approves all final versions.

# References

Smith, J. (2020). Policy change in practice. Australian Government Press.
Jones, A. (2021). Governance review findings. Australian Government Press.
"""
    findings = run_rules(text)
    # We don't assert specific findings, just that the call succeeds and
    # document-level gating doesn't incorrectly drop everything.
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# Legacy parity baseline
# ---------------------------------------------------------------------------

_PARITY_CORPUS = [
    # 0: smoke text (all three taxonomies)
    _SMOKE_TEXT,
    # 1: Step 1 noisy example
    _STEP_1_TEXT,
    # 2: minimal paragraph
    "The committee reviewed the submission and approved the policy.",
    # 3: structured doc with heading + list
    "# Overview\n\n- Item one\n- Item two\n- Item three\n\nThe policy covers all cases.",
    # 4: text with numbers and dates
    "On 3 March 2024, the department published 15 guidelines for review.",
    # 5: passive voice
    "The report was written by the committee. The policy was approved by management.",
    # 6: abbreviations and acronyms
    "The APS must comply with WHS Act requirements. The PGPA Act governs this.",
    # 7: legislation reference
    "Under the Public Governance, Performance and Accountability Act 2013, agencies must report.",
    # 8: citation heavy
    "Authors (2020) argue that policy (Smith, 2020; Jones, 2021) matters.",
    # 9: empty + whitespace edge cases
    "",
]


def test_legacy_parity_baseline():
    """Run both dispatchers on a 10-doc corpus and compute Jaccard similarity.

    No threshold is asserted — Phase 5 will calibrate this metric.
    Overlap tuples are (rule_id, start_char, end_char).
    """
    import logic.dispatcher as legacy

    jaccard_scores: list[float] = []
    over_retrieved: list[str] = []  # rules retrieved on every segment

    for i, doc_text in enumerate(_PARITY_CORPUS):
        legacy_findings = legacy.run_rules(doc_text)
        indexed_findings = run_rules(doc_text)

        legacy_set = {
            (f["rule_id"], f["start_char"], f["end_char"])
            for f in legacy_findings
        }
        indexed_set = {
            (f["rule_id"], f["start_char"], f["end_char"])
            for f in indexed_findings
        }

        if not legacy_set and not indexed_set:
            jaccard_scores.append(1.0)
        elif not legacy_set or not indexed_set:
            jaccard_scores.append(0.0)
        else:
            intersection = legacy_set & indexed_set
            union = legacy_set | indexed_set
            jaccard_scores.append(len(intersection) / len(union))

    mean_jaccard = sum(jaccard_scores) / len(jaccard_scores)
    print(
        f"\nLegacy vs indexed Jaccard parity — "
        f"mean: {mean_jaccard:.3f}, "
        f"per-doc: {[f'{s:.2f}' for s in jaccard_scores]}"
    )

    # Phase 5 will turn this into an assertion; for now just ensure the run
    # completes without errors and the similarity is finite.
    assert 0.0 <= mean_jaccard <= 1.0
