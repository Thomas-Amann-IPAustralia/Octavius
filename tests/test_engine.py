"""Tests for the Octavius linting engine and passive-voice rule."""

from logic.engine import get_spacy_status, lint_text
from logic.rules import RULES


def test_spacy_loads():
    assert get_spacy_status() is True


def test_passive_voice_detected():
    text = "The report was written by the team."
    findings = lint_text(text, RULES)
    assert len(findings) >= 1
    assert findings[0]["rule_id"] == "PASSIVE-VOICE-001"
    assert findings[0]["severity"] == "warn"
    assert "was written" in text[findings[0]["start_char"] : findings[0]["end_char"]]


def test_active_voice_clean():
    text = "The team wrote the report."
    findings = lint_text(text, RULES)
    assert findings == []


def test_multiple_passives():
    text = "The cake was eaten and the song was sung."
    findings = lint_text(text, RULES)
    assert len(findings) == 2


def test_finding_keys():
    text = "Mistakes were made."
    findings = lint_text(text, RULES)
    assert len(findings) >= 1
    required_keys = {"start_char", "end_char", "rule_id", "message", "severity", "suggestion"}
    assert required_keys.issubset(findings[0].keys())


def test_empty_text():
    findings = lint_text("", RULES)
    assert findings == []
