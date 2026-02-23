import pytest
import spacy
from logic.lint import lint_text, HEURISTIC_FUNCTIONS

def test_collective_noun_agreement_heuristic():
    rule_id = "APS-GPC-Nouns-R-004"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "warn"}]
    # Even if category is heuristic or regex, my refined logic prefers the heuristic mapping
    text = "The committee are meeting today."
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id
    assert "committee are" in text[findings[0]["start_char"]:findings[0]["end_char"]]

def test_hyphenated_modifier_heuristic():
    rule_id = "APS-GPC-Adjectives-H-002"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "warn"}]
    text = "This is a well written report."
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id
    assert "well written" in text[findings[0]["start_char"]:findings[0]["end_char"]]

def test_complete_sentence_heuristic():
    rule_id = "APS-GPC-Partsofsentences-H-001"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "error"}]
    text = "A very long phrase without a verb or subject."
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id

def test_exclamation_marks_heuristic():
    rule_id = "APS-GPC-Exclamationmarks-H-001"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "error"}]
    text = "Stop right there!"
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id

def test_a_vs_an_heuristic():
    rule_id = "APS-GPC-Determiners-R-001"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "warn"}]
    text = "An university."
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id
    assert "An university" in text[findings[0]["start_char"]:findings[0]["end_char"]]

def test_ordinal_pairing_heuristic():
    rule_id = "APS-GPC-Ordinalnumbers-H-002"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "info"}]
    text = "Firstly, we should eat. Finally, we sleep." # Missing "Secondly"
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == rule_id

def test_australian_government_casing_heuristic():
    rule_id = "APS-GPC-Governmentterms-H-001"
    rules = [{"id": rule_id, "category": "heuristic", "message": "msg", "severity": "warn"}]
    text = "The Australian government is here." # 'government' should be 'Government'
    findings = lint_text(text, rules)
    assert any(f["rule_id"] == rule_id for f in findings)
