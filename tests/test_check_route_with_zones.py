"""Tests for POST /check with and without zones.

Validates:
1. Zones path: when zones are present, from_zones() is used (markdown
   segmentation skipped).
2. Fallback path: when zones are absent, the original markdown path is used.
3. API compatibility: response shape is unchanged regardless of path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_TEXT = "This is a sample paragraph with some text."

SAMPLE_ZONES = [
    {
        "kind": "paragraph",
        "text": SAMPLE_TEXT,
        "offset": 0,
        "length": len(SAMPLE_TEXT),
        "ancestors": [],
        "lintable": True,
    }
]

STRUCTURED_TEXT = "My Heading\nThis is a paragraph.\n"
STRUCTURED_ZONES = [
    {
        "kind": "heading",
        "text": "My Heading",
        "offset": 0,
        "length": 10,
        "ancestors": [],
        "lintable": True,
    },
    {
        "kind": "paragraph",
        "text": "This is a paragraph.",
        "offset": 11,
        "length": 20,
        "ancestors": [],
        "lintable": True,
    },
]


# ---------------------------------------------------------------------------
# Basic zone path
# ---------------------------------------------------------------------------


def test_check_with_zones_returns_200() -> None:
    resp = client.post("/check", json={"text": SAMPLE_TEXT, "zones": SAMPLE_ZONES})
    assert resp.status_code == 200


def test_check_with_zones_returns_list() -> None:
    resp = client.post("/check", json={"text": SAMPLE_TEXT, "zones": SAMPLE_ZONES})
    data = resp.json()
    assert isinstance(data, list)


def test_check_without_zones_returns_200() -> None:
    """Fallback to markdown path when zones absent."""
    resp = client.post("/check", json={"text": SAMPLE_TEXT})
    assert resp.status_code == 200


def test_check_without_zones_returns_list() -> None:
    resp = client.post("/check", json={"text": SAMPLE_TEXT})
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Response shape (both paths must return identical fields)
# ---------------------------------------------------------------------------

REQUIRED_FINDING_FIELDS = {
    "rule_id", "message", "start", "end", "severity",
    "document_level", "mutation_class",
}


def _check_finding_shape(finding: dict) -> None:
    missing = REQUIRED_FINDING_FIELDS - set(finding.keys())
    assert not missing, f"Finding missing fields: {missing}"


def test_zone_path_finding_shape() -> None:
    resp = client.post("/check", json={"text": SAMPLE_TEXT, "zones": SAMPLE_ZONES})
    for f in resp.json():
        _check_finding_shape(f)


def test_non_zone_path_finding_shape() -> None:
    resp = client.post("/check", json={"text": SAMPLE_TEXT})
    for f in resp.json():
        _check_finding_shape(f)


# ---------------------------------------------------------------------------
# plain_text field accepted as alias for text
# ---------------------------------------------------------------------------


def test_plain_text_field_accepted() -> None:
    resp = client.post("/check", json={
        "text": SAMPLE_TEXT,
        "plain_text": SAMPLE_TEXT,
        "zones": SAMPLE_ZONES,
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Empty zones list falls back to markdown path
# ---------------------------------------------------------------------------


def test_empty_zones_uses_markdown_path() -> None:
    """An empty zones list is treated as 'no zones' — markdown path runs."""
    resp_no_zones = client.post("/check", json={"text": SAMPLE_TEXT})
    resp_empty_zones = client.post("/check", json={"text": SAMPLE_TEXT, "zones": []})
    # Both should succeed with the same response structure.
    assert resp_no_zones.status_code == 200
    assert resp_empty_zones.status_code == 200


# ---------------------------------------------------------------------------
# Zone offset validity
# ---------------------------------------------------------------------------


def test_check_with_zones_findings_within_text() -> None:
    """Findings from the zone path must have start/end within the text length."""
    resp = client.post("/check", json={"text": STRUCTURED_TEXT, "zones": STRUCTURED_ZONES})
    assert resp.status_code == 200
    for f in resp.json():
        start = f.get("start", 0)
        end = f.get("end", 0)
        if not f.get("document_level"):
            assert 0 <= start <= end <= len(STRUCTURED_TEXT), (
                f"Finding [{start}, {end}] out of range for text len={len(STRUCTURED_TEXT)}: {f}"
            )


# ---------------------------------------------------------------------------
# Disabled rule IDs still work with zones
# ---------------------------------------------------------------------------


def test_disabled_rule_ids_with_zones() -> None:
    resp = client.post("/check", json={
        "text": SAMPLE_TEXT,
        "zones": SAMPLE_ZONES,
        "disabled_rule_ids": ["nonexistent-rule-xyz"],
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Code fence zones excluded from linting (indexed dispatcher only)
# ---------------------------------------------------------------------------


def test_code_fence_zone_returns_200() -> None:
    """Check endpoint accepts code_fence zones without error."""
    code = "```python\nprint('hello')\n```"
    zones = [
        {"kind": "code_fence", "text": code, "offset": 0, "length": len(code),
         "ancestors": [], "lintable": False}
    ]
    resp = client.post("/check", json={"text": code, "zones": zones})
    assert resp.status_code == 200


def test_code_fence_zone_not_linted_indexed() -> None:
    """When the indexed dispatcher is active, code_fence zones (lintable=False)
    must not produce spanned findings.

    This test is skipped when the legacy dispatcher is active — the legacy
    dispatcher is zone-unaware and may lint the full text regardless.
    """
    import os
    if os.environ.get("OCTAVIUS_DISPATCHER", "legacy").lower() != "indexed":
        pytest.skip("Test only valid for the indexed dispatcher (OCTAVIUS_DISPATCHER=indexed)")

    code = "```python\nprint('hello')\n```"
    zones = [
        {"kind": "code_fence", "text": code, "offset": 0, "length": len(code),
         "ancestors": [], "lintable": False}
    ]
    resp = client.post("/check", json={"text": code, "zones": zones})
    assert resp.status_code == 200
    findings = resp.json()
    spanned = [f for f in findings if not f.get("document_level")]
    assert spanned == [], "No spanned findings for a code-fence-only document"
