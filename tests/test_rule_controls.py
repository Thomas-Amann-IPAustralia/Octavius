
import pytest
from logic.lint import lint_text

def test_rule_controls_enabled():
    text = "This is a sentence."
    rules = [
        {
            "id": "RULE-1",
            "category": "regex",
            "pattern": "sentence",
            "severity": "warn",
            "message": "Found sentence",
            "enabled": True
        }
    ]
    findings = lint_text(text, rules)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "RULE-1"

    # Now disable the rule
    rules[0]["enabled"] = False
    findings = lint_text(text, rules)
    assert len(findings) == 0

def test_rule_controls_severity_override():
    text = "This is a sentence."
    rules = [
        {
            "id": "RULE-1",
            "category": "regex",
            "pattern": "sentence",
            "severity": "warn",
            "message": "Found sentence",
            "enabled": True
        }
    ]
    findings = lint_text(text, rules)
    assert findings[0]["severity"] == "warn"

    # Now override severity
    rules[0]["severity_override"] = "error"
    findings = lint_text(text, rules)
    assert findings[0]["severity"] == "error"
