import pytest
import spacy
from logic.lint import lint_text, HEURISTIC_FUNCTIONS

def test_regex_rule():
    rules = [
        {
            "id": "test-regex",
            "category": "regex",
            "pattern": r"\btest\b",
            "message": "Found test",
            "severity": "warn"
        }
    ]
    text = "This is a test case."
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "test-regex"
    assert findings[0]["start_char"] == 10
    assert findings[0]["end_char"] == 14

def test_passive_voice_heuristic():
    # Only run if spaCy is available
    nlp = spacy.load("en_core_web_sm")
    if nlp:
        rule_id = "APS-GPC-Partsofsentences-H-009"
        rules = [
            {
                "id": rule_id,
                "category": "heuristic",
                "message": "Passive voice detected",
                "severity": "info"
            }
        ]
        text = "The book was read by him."
        findings = lint_text(text, rules)
        assert len(findings) == 1
        assert findings[0]["rule_id"] == rule_id
        # "was read" should be flagged
        assert "was read" in text[findings[0]["start_char"]:findings[0]["end_char"]]

def test_multiple_findings():
    rules = [
        {
            "id": "regex-1",
            "category": "regex",
            "pattern": "apple",
            "message": "No apples",
            "severity": "error"
        },
        {
            "id": "regex-2",
            "category": "regex",
            "pattern": "banana",
            "message": "No bananas",
            "severity": "error"
        }
    ]
    text = "I have an apple and a banana."
    findings = lint_text(text, rules)
    assert len(findings) == 2
    assert findings[0]["rule_id"] == "regex-1"
    assert findings[1]["rule_id"] == "regex-2"

def test_empty_text():
    rules = [{"id": "r1", "category": "regex", "pattern": "x", "message": "m"}]
    findings = lint_text("", rules)
    assert findings == []

def test_invalid_regex():
    rules = [
        {
            "id": "invalid-regex",
            "category": "regex",
            "pattern": "[",
            "message": "Invalid",
            "severity": "error"
        }
    ]
    # Should not crash, but return a system finding
    findings = lint_text("some text", rules)
    assert len(findings) == 1
    assert "SYS-REGEX-ERROR" in findings[0]["rule_id"]
