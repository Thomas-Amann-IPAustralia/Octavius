"""Round-trip test: required_features + mutation_class through publish.py → loader.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helper — build a complete rule row
# ---------------------------------------------------------------------------

def _make_rule(**overrides) -> dict:
    base = {
        "rule_id": "test--roundtrip-001",
        "source_url": "https://www.stylemanual.gov.au/test",
        "source_file": "content/test.md",
        "rule_summary": "Use en dashes for year spans.",
        "rule_detail": "Year spans should use an en dash, not a hyphen.",
        "taxonomy": "regex",
        "discretionary_flag": False,
        "method": "regex",
        "requires": [],
        "method_notes": "Regex match on YYYY-YYYY pattern.",
        "trigger_code": r"r'\b\d{4}-\d{4}\b'",
        "ui_flag": "Year span uses hyphen. Use an en dash (–).",
        "test_fire": ["The report covers 2019-2021."],
        "test_no_fire": ["The report was published in 2021."],
        "lookup_list": [],
        "test_result": "pass",
        "test_run_at": "2026-05-05T00:00:00Z",
        "error_log": None,
        "correction_model": None,
        "extracted_at": "2026-04-14T00:00:00Z",
        "code_generated_at": "2026-04-15T00:00:00Z",
        # Phase 3.5
        "required_features": {
            "all_of": ["HAS_EN_DASH", "HAS_CARDINAL"],
            "any_of": ["ZONE_PARAGRAPH", "ZONE_LIST_BULLET"],
            "none_of": ["EXEMPT_CODE_SNIPPET", "EXEMPT_QUOTED_CONTENT"],
        },
        "mutation_class": "safe_replace",
    }
    base.update(overrides)
    return base


def _write_jsonl(rules: list[dict], path: Path) -> None:
    with open(path, "w") as f:
        for rule in rules:
            f.write(json.dumps(rule) + "\n")


def _run_publish(jsonl_path: Path, parquet_path: Path) -> None:
    """Run src/publish.main() with patched file paths."""
    import src.publish as pub

    with (
        patch.object(pub, "RULES_DRAFT_FILE", jsonl_path),
        patch.object(pub, "PARQUET_FILE", parquet_path),
        patch.object(pub, "METADATA_FILE", parquet_path.with_suffix(".json")),
        patch.object(pub, "PUBLISHED_DIR", parquet_path.parent),
        patch.object(pub, "REPO_ROOT", parquet_path.parent),
        patch("src.publish.git_commit"),
    ):
        pub.main()


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def test_required_features_and_mutation_class_survive_roundtrip(self, tmp_path):
        """A fully-populated rule survives publish.py → loader.py intact."""
        rule = _make_rule()
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        from logic.rulebook.loader import load_rules
        rules = load_rules(parquet_path)

        assert len(rules) == 1
        loaded = rules[0]

        # mutation_class
        assert loaded["mutation_class"] == "safe_replace"

        # required_features reconstructed from split columns
        rf = loaded["required_features"]
        assert rf is not None
        assert set(rf["all_of"]) == {"HAS_EN_DASH", "HAS_CARDINAL"}
        assert set(rf["any_of"]) == {"ZONE_PARAGRAPH", "ZONE_LIST_BULLET"}
        assert set(rf["none_of"]) == {"EXEMPT_CODE_SNIPPET", "EXEMPT_QUOTED_CONTENT"}

    def test_null_required_features_survives_roundtrip(self, tmp_path):
        """A rule with null required_features → None after round-trip."""
        rule = _make_rule(required_features=None, mutation_class=None)
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        from logic.rulebook.loader import load_rules
        rules = load_rules(parquet_path)
        assert len(rules) == 1
        assert rules[0]["required_features"] is None
        assert rules[0]["mutation_class"] is None

    def test_parquet_schema_has_new_columns(self, tmp_path):
        """Published Parquet must contain the four new Phase 3.5 column names."""
        rule = _make_rule()
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        table = pq.read_table(str(parquet_path))
        names = table.schema.names
        assert "required_features_all_of" in names
        assert "required_features_any_of" in names
        assert "required_features_none_of" in names
        assert "mutation_class" in names

    def test_requires_rewrite_mutation_class(self, tmp_path):
        rule = _make_rule(
            rule_id="test--roundtrip-002",
            required_features={
                "all_of": ["LING_PASSIVE_VOICE"],
                "any_of": [],
                "none_of": ["EXEMPT_QUOTED_CONTENT"],
            },
            mutation_class="requires_rewrite",
        )
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        from logic.rulebook.loader import load_rules
        rules = load_rules(parquet_path)
        assert rules[0]["mutation_class"] == "requires_rewrite"

    def test_human_review_mutation_class(self, tmp_path):
        rule = _make_rule(
            rule_id="test--roundtrip-003",
            required_features={
                "all_of": [],
                "any_of": ["LING_LONG_SENTENCE"],
                "none_of": [],
            },
            mutation_class="human_review",
        )
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        from logic.rulebook.loader import load_rules
        rules = load_rules(parquet_path)
        assert rules[0]["mutation_class"] == "human_review"

    def test_acceptance_check_columns_present(self, tmp_path):
        """Mirrors the acceptance check: 'required_features_all_of' or 'required_features' in schema names, and 'mutation_class'."""
        rule = _make_rule()
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        table = pq.read_table(str(parquet_path))
        ns = table.schema.names
        assert ("required_features" in ns or "required_features_all_of" in ns)
        assert "mutation_class" in ns

    def test_multiple_rules_mixed_annotation(self, tmp_path):
        """Annotated and unannotated rules in the same parquet work correctly."""
        rule_annotated = _make_rule(rule_id="test--roundtrip-010")
        rule_unannotated = _make_rule(
            rule_id="test--roundtrip-011",
            required_features=None,
            mutation_class=None,
        )
        jsonl_path = tmp_path / "rules_working_draft.jsonl"
        parquet_path = tmp_path / "rulebook.parquet"

        _write_jsonl([rule_annotated, rule_unannotated], jsonl_path)
        _run_publish(jsonl_path, parquet_path)

        from logic.rulebook.loader import load_rules
        rules = load_rules(parquet_path)
        assert len(rules) == 2

        by_id = {r["rule_id"]: r for r in rules}
        assert by_id["test--roundtrip-010"]["required_features"] is not None
        assert by_id["test--roundtrip-010"]["mutation_class"] == "safe_replace"
        assert by_id["test--roundtrip-011"]["required_features"] is None
        assert by_id["test--roundtrip-011"]["mutation_class"] is None
