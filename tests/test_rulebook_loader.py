"""Tests for logic/rulebook/loader.py."""

from __future__ import annotations

import pytest

from logic.rulebook.loader import load_rules


def test_total_rule_count():
    rules = load_rules()
    assert len(rules) == 801


def test_taxonomy_counts():
    rules = load_rules()
    by_tax = {}
    for r in rules:
        by_tax[r["taxonomy"]] = by_tax.get(r["taxonomy"], 0) + 1
    assert by_tax["lookup"] == 415
    assert by_tax["regex"] == 124
    assert by_tax["structural"] == 262


def test_compiled_rule_fields():
    rules = load_rules()
    required = {"rule_id", "taxonomy", "ui_flag", "rule_summary", "source_url", "severity", "check"}
    for rule in rules[:10]:
        assert required.issubset(rule.keys())
        assert callable(rule["check"])


def test_check_callable_returns_list():
    rules = load_rules()
    # Each check() with empty text must return a list without raising.
    for rule in rules[:20]:
        result = rule["check"]("")
        assert isinstance(result, list)


def test_raises_on_missing_parquet():
    with pytest.raises(FileNotFoundError):
        load_rules("/nonexistent/path/rulebook.parquet")
