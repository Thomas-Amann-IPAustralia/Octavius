"""Tests for GET /rules and GET /taxonomies."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

EXPECTED_RULE_FIELDS = {"rule_id", "taxonomy", "ui_flag", "rule_summary", "source_url", "severity"}
EXPECTED_TAXONOMIES = {"lookup", "regex", "structural"}
EXPECTED_COUNTS = {"lookup": 415, "regex": 124, "structural": 262}


def test_rules_returns_list():
    resp = client.get("/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_rules_count():
    resp = client.get("/rules")
    data = resp.json()
    # S1 loader produces 801 passing rules (415 lookup + 124 regex + 262 structural)
    assert len(data) == 801


def test_rules_fields_present():
    resp = client.get("/rules")
    data = resp.json()
    for entry in data[:10]:  # spot-check first 10
        assert EXPECTED_RULE_FIELDS.issubset(entry.keys()), (
            f"Missing fields: {EXPECTED_RULE_FIELDS - entry.keys()} in {entry}"
        )


def test_taxonomies_returns_three():
    resp = client.get("/taxonomies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3


def test_taxonomies_ids():
    resp = client.get("/taxonomies")
    data = resp.json()
    ids = {entry["id"] for entry in data}
    assert ids == EXPECTED_TAXONOMIES


def test_taxonomies_counts():
    resp = client.get("/taxonomies")
    data = resp.json()
    for entry in data:
        assert entry["rule_count"] == EXPECTED_COUNTS[entry["id"]], (
            f"Unexpected count for {entry['id']}: {entry['rule_count']}"
        )
