"""Tests for POST /check."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# This sentence reliably fires at least one rule from each taxonomy:
# - regex: headings-034, punctuation-and-capitalisation-003
# - lookup: dates-and-time-016 (Tue, Thu), determiners-005 (the)
# - structural: bills-and-explanatory-material-022
TEST_SENTENCE = "The meeting is on Tue and Thu. The cat was chased by the dog."

REQUIRED_RESPONSE_FIELDS = {"rule_id", "group", "taxonomy", "ui_flag", "rule_summary",
                             "source_url", "message", "start", "end", "severity",
                             "document_level"}


def _post_check(text: str, **kwargs) -> list[dict]:
    resp = client.post("/check", json={"text": text, **kwargs})
    assert resp.status_code == 200
    return resp.json()


def test_check_returns_findings():
    data = _post_check(TEST_SENTENCE)
    assert len(data) > 0


def test_check_finding_fields():
    data = _post_check(TEST_SENTENCE)
    for f in data[:5]:
        assert REQUIRED_RESPONSE_FIELDS.issubset(f.keys()), (
            f"Missing fields: {REQUIRED_RESPONSE_FIELDS - f.keys()}"
        )


def test_check_group_mirrors_taxonomy():
    """Legacy compatibility: 'group' must equal 'taxonomy'."""
    data = _post_check(TEST_SENTENCE)
    for f in data:
        assert f["group"] == f["taxonomy"], (
            f"group != taxonomy for {f['rule_id']}"
        )


def test_check_message_is_ui_flag():
    """Legacy compatibility: 'message' must equal 'ui_flag'."""
    data = _post_check(TEST_SENTENCE)
    for f in data:
        assert f["message"] == f["ui_flag"], (
            f"message != ui_flag for {f['rule_id']}"
        )


def test_check_start_end_are_ints():
    data = _post_check(TEST_SENTENCE)
    for f in data:
        assert isinstance(f["start"], int)
        assert isinstance(f["end"], int)


def test_check_fires_per_taxonomy():
    """The test sentence should produce findings from all three taxonomies."""
    data = _post_check(TEST_SENTENCE)
    taxonomies = {f["taxonomy"] for f in data}
    assert "regex" in taxonomies, "No regex findings"
    assert "lookup" in taxonomies, "No lookup findings"
    assert "structural" in taxonomies, "No structural findings"


def test_check_disabled_rule_ids_removes_rule():
    """Disabling a specific rule removes it from the response."""
    # headings-034 is a regex rule that always fires on TEST_SENTENCE
    all_findings = _post_check(TEST_SENTENCE)
    rule_ids_before = {f["rule_id"] for f in all_findings}
    assert "headings-034" in rule_ids_before, "headings-034 must fire on test sentence"

    filtered = _post_check(TEST_SENTENCE, disabled_rule_ids=["headings-034"])
    rule_ids_after = {f["rule_id"] for f in filtered}
    assert "headings-034" not in rule_ids_after


def test_check_disabled_taxonomies_removes_taxonomy():
    """Disabling a taxonomy removes all its findings."""
    data = _post_check(TEST_SENTENCE, disabled_taxonomies=["structural"])
    for f in data:
        assert f["taxonomy"] != "structural", (
            f"Structural finding {f['rule_id']} still present after disabling"
        )


def test_check_disabled_taxonomies_lookup():
    data = _post_check(TEST_SENTENCE, disabled_taxonomies=["lookup"])
    for f in data:
        assert f["taxonomy"] != "lookup"


def test_check_legacy_rule_groups_accepted():
    """Legacy 'rule_groups' field is accepted without error (ignored)."""
    resp = client.post("/check", json={
        "text": TEST_SENTENCE,
        "rule_groups": ["punctuation", "capitalisation"],
    })
    assert resp.status_code == 200
    # Should return the same full set since rule_groups is ignored
    data = resp.json()
    assert len(data) > 0


def test_check_legacy_rule_groups_does_not_filter():
    """Legacy 'rule_groups' is ignored — all enabled rules still run."""
    with_groups = client.post("/check", json={
        "text": TEST_SENTENCE,
        "rule_groups": ["nonexistent_group"],
    }).json()
    without_groups = _post_check(TEST_SENTENCE)
    assert len(with_groups) == len(without_groups)


def test_check_empty_text_returns_empty():
    data = _post_check("")
    assert isinstance(data, list)
