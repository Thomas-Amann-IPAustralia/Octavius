"""Dispatcher smoke tests."""

from __future__ import annotations

from logic.dispatcher import run_rules

# A paragraph that exercises all three taxonomies:
# - regex  : "Style Manual (Style Manual)" → how-cite-style-manual-007
# - lookup : "alphabetically by author name" → about-style-manual--changelog-001
# - structural: author-date citation + References section → how-cite-style-manual-014
_SMOKE_TEXT = """\
Use the Australian Government Style Manual (Style Manual) when writing.
Arrange the works alphabetically by author name.
The policy improved service delivery (Smith, 2020).

References
Smith, J. (2020). Policy change in practice. Australian Government Press.
"""


def test_smoke_no_exception():
    findings = run_rules(_SMOKE_TEXT)
    assert isinstance(findings, list)


def test_smoke_produces_findings():
    findings = run_rules(_SMOKE_TEXT)
    assert len(findings) >= 1


def test_findings_sorted():
    findings = run_rules(_SMOKE_TEXT)
    for i in range(len(findings) - 1):
        a, b = findings[i], findings[i + 1]
        assert (a["start_char"], a["rule_id"]) <= (b["start_char"], b["rule_id"])


def test_smoke_has_regex_finding():
    findings = run_rules(_SMOKE_TEXT)
    assert any(f["taxonomy"] == "regex" for f in findings)


def test_smoke_has_lookup_finding():
    findings = run_rules(_SMOKE_TEXT)
    assert any(f["taxonomy"] == "lookup" for f in findings)


def test_smoke_has_structural_finding():
    findings = run_rules(_SMOKE_TEXT)
    assert any(f["taxonomy"] == "structural" for f in findings)


def test_disable_structural_taxonomy():
    findings = run_rules(_SMOKE_TEXT, disabled_taxonomies={"structural"})
    structural = [f for f in findings if f["taxonomy"] == "structural"]
    assert structural == []


def test_disable_lookup_taxonomy():
    findings = run_rules(_SMOKE_TEXT, disabled_taxonomies={"lookup"})
    assert all(f["taxonomy"] != "lookup" for f in findings)


def test_disable_specific_rule_id():
    rule_id = "about-style-manual--changelog-001"
    all_findings = run_rules(_SMOKE_TEXT)
    filtered = run_rules(_SMOKE_TEXT, disabled_rule_ids={rule_id})
    assert not any(f["rule_id"] == rule_id for f in filtered)
    # Some findings may remain
    assert len(filtered) <= len(all_findings)


def test_empty_text_no_exception():
    findings = run_rules("")
    assert isinstance(findings, list)


def test_finding_required_fields():
    findings = run_rules(_SMOKE_TEXT)
    required = {"start_char", "end_char", "rule_id", "taxonomy", "ui_flag",
                "rule_summary", "source_url", "severity", "document_level"}
    for f in findings[:20]:
        assert required.issubset(f.keys()), f"Missing fields in finding: {f}"
