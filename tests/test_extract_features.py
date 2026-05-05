"""Tests for src/extract_features.py — Phase 3.5 feature authoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract_features import (
    VALID_MUTATION_CLASSES,
    build_user_message,
    validate_response,
)
from logic.features.vocabulary import validate_feature, EXEMPT_FEATURES


# ---------------------------------------------------------------------------
# Fixtures — hand-crafted rule rows
# ---------------------------------------------------------------------------

def _base_rule(**kwargs) -> dict:
    """Return a minimal passing rule with overridable fields."""
    base = {
        "rule_id": "test--rule-001",
        "source_url": "https://www.stylemanual.gov.au/test",
        "source_file": "content/test.md",
        "rule_summary": "Use en dashes for year spans.",
        "rule_detail": "Year spans should use an en dash, not a hyphen.",
        "taxonomy": "regex",
        "discretionary_flag": False,
        "test_result": "pass",
        "method": "regex",
        "trigger_code": r"r'\b\d{4}-\d{4}\b'",
        "ui_flag": "Year span uses hyphen. Use an en dash (–).",
        "test_fire": ["The report covers 2019-2021."],
        "test_no_fire": ["The report was published in 2021."],
        "lookup_list": [],
        "required_features": None,
        "mutation_class": None,
    }
    base.update(kwargs)
    return base


# Six hand-crafted rules covering the four worked examples plus two edge cases
RULE_REGNAL = _base_rule(
    rule_id="test--regnal-001",
    rule_summary="Write regnal numerals using Roman numerals, not Arabic numerals.",
    taxonomy="regex",
    trigger_code=r"r'\b(King|Queen|Prince|Princess|Emperor|Empress)\s+\w+\s+\d+\b'",
    test_fire=["Elizabeth 2 visited the school."],
    test_no_fire=["Elizabeth II visited the school."],
)

RULE_PASSIVE = _base_rule(
    rule_id="test--passive-001",
    rule_summary="Avoid passive voice in body paragraphs.",
    taxonomy="spacy",
    trigger_code="# spacy passive voice detection",
    test_fire=["The report was written by the team."],
    test_no_fire=["The team wrote the report."],
)

RULE_DATE = _base_rule(
    rule_id="test--date-001",
    rule_summary="Use the long-form date format: day month year.",
    taxonomy="regex",
    trigger_code=r"r'\b\d{4}-\d{2}-\d{2}\b'",
    test_fire=["Submit the form by 2024-01-15."],
    test_no_fire=["Submit the form by 15 January 2024."],
)

RULE_BUREAUCRATIC = _base_rule(
    rule_id="test--bureaucratic-001",
    rule_summary="Avoid bureaucratic phrases in body text.",
    taxonomy="lookup",
    trigger_code="# lookup rule",
    lookup_list=["pursuant to", "in accordance with", "notwithstanding"],
    test_fire=["Pursuant to the legislation, you must comply."],
    test_no_fire=["Under the legislation, you must comply."],
)

# Edge case: already-annotated rule (should be skipped in submit)
RULE_ALREADY_DONE = _base_rule(
    rule_id="test--done-001",
    rule_summary="Use sentence case for headings.",
    taxonomy="structural",
    trigger_code="# structural rule",
    required_features={"all_of": ["ZONE_HEADING"], "any_of": [], "none_of": []},
    mutation_class="safe_replace",
)

# Edge case: failing rule (should not be submitted)
RULE_FAILING = _base_rule(
    rule_id="test--fail-001",
    rule_summary="A failing rule.",
    taxonomy="regex",
    trigger_code="BROKEN CODE",
    test_result="fail",
)


# ---------------------------------------------------------------------------
# Tests for validate_response()
# ---------------------------------------------------------------------------

class TestValidateResponse:

    def test_valid_safe_replace(self):
        data = {
            "required_features": {
                "all_of": ["HAS_CARDINAL", "PATTERN_REGNAL_NUMERAL_SHAPE"],
                "any_of": [],
                "none_of": ["EXEMPT_IDENTIFIER", "EXEMPT_CODE_SNIPPET"],
            },
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert err is None
        assert validated["mutation_class"] == "safe_replace"
        assert validated["required_features"]["all_of"] == ["HAS_CARDINAL", "PATTERN_REGNAL_NUMERAL_SHAPE"]
        assert "EXEMPT_IDENTIFIER" in validated["required_features"]["none_of"]

    def test_valid_requires_rewrite(self):
        data = {
            "required_features": {
                "all_of": ["LING_PASSIVE_VOICE"],
                "any_of": ["ZONE_PARAGRAPH", "ZONE_LIST_BULLET"],
                "none_of": ["EXEMPT_QUOTED_CONTENT", "ANCESTOR_BLOCKQUOTE"],
            },
            "mutation_class": "requires_rewrite",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert err is None
        assert validated["mutation_class"] == "requires_rewrite"

    def test_valid_human_review(self):
        data = {
            "required_features": {
                "all_of": [],
                "any_of": ["LING_PASSIVE_VOICE", "LING_LONG_SENTENCE"],
                "none_of": ["EXEMPT_QUOTED_CONTENT"],
            },
            "mutation_class": "human_review",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert err is None
        assert validated["mutation_class"] == "human_review"

    def test_valid_empty_all_slots(self):
        """A rule with all empty slots and a valid mutation_class is accepted."""
        data = {
            "required_features": {"all_of": [], "any_of": [], "none_of": []},
            "mutation_class": "human_review",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert err is None

    # --- Rejection cases ---

    def test_exempt_in_all_of_rejected(self):
        """EXEMPT_* feature in all_of must be rejected."""
        data = {
            "required_features": {
                "all_of": ["EXEMPT_CODE_SNIPPET"],
                "any_of": [],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None
        assert "EXEMPT_" in err
        assert "all_of" in err

    def test_exempt_in_any_of_rejected(self):
        """EXEMPT_* feature in any_of must be rejected."""
        data = {
            "required_features": {
                "all_of": [],
                "any_of": ["EXEMPT_URL"],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None
        assert "any_of" in err

    def test_unknown_feature_name_rejected(self):
        """A feature name not in the vocabulary must be rejected."""
        data = {
            "required_features": {
                "all_of": ["PATTERN_INVENTED_FEATURE"],
                "any_of": [],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None
        assert "PATTERN_INVENTED_FEATURE" in err

    def test_threshold_feature_name_rejected(self):
        """Feature names encoding numeric thresholds must be rejected."""
        data = {
            "required_features": {
                "all_of": ["LING_LONG_SENTENCE_25P"],
                "any_of": [],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None

    def test_unknown_mutation_class_rejected(self):
        """An unrecognised mutation_class must be rejected."""
        data = {
            "required_features": {"all_of": [], "any_of": [], "none_of": []},
            "mutation_class": "auto_fix",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None
        assert "mutation_class" in err

    def test_missing_mutation_class_rejected(self):
        data = {
            "required_features": {"all_of": [], "any_of": [], "none_of": []},
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert "mutation_class" in err

    def test_missing_required_features_rejected(self):
        data = {"mutation_class": "safe_replace"}
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert "required_features" in err

    def test_non_json_response(self):
        """Non-JSON text must not reach validate_response without a parse error."""
        text = "I cannot determine the features for this rule."
        with pytest.raises(Exception):
            json.loads(text)

    def test_required_features_not_dict(self):
        data = {
            "required_features": ["HAS_CARDINAL"],
            "mutation_class": "safe_replace",
        }
        validated, err = validate_response(data, validate_feature, EXEMPT_FEATURES)
        assert validated is None
        assert err is not None


# ---------------------------------------------------------------------------
# Tests for collect() — JSONL output via mocked OpenAI client
# ---------------------------------------------------------------------------

def _make_batch_result(rule_id: str, response_text: str, status_code: int = 200) -> dict:
    """Build a fake OpenAI Batch API result line."""
    return {
        "custom_id": rule_id,
        "response": {
            "status_code": status_code,
            "body": {
                "choices": [{"message": {"content": response_text}}]
            },
        },
    }


def _make_rules_jsonl(rules: list[dict], tmp_path: Path) -> Path:
    """Write rules to a temporary JSONL file and return its path."""
    jsonl_path = tmp_path / "rules_working_draft.jsonl"
    with open(jsonl_path, "w") as f:
        for rule in rules:
            f.write(json.dumps(rule) + "\n")
    return jsonl_path


def _run_collect_with_mock_responses(
    rules: list[dict],
    responses: dict[str, str],
    tmp_path: Path,
) -> list[dict]:
    """
    Run extract_features.collect() with mocked OpenAI and filesystem,
    return the resulting rules list.
    """
    import src.extract_features as ef

    jsonl_path = _make_rules_jsonl(rules, tmp_path)
    batch_state = {
        "phase": "3.5",
        "batch_ids": ["batch_test_001"],
        "submitted_at": "2026-05-05T00:00:00Z",
        "processed_rule_ids": [r["rule_id"] for r in rules],
    }
    batch_state_path = tmp_path / "batch_state.json"
    batch_state_path.write_text(json.dumps(batch_state))

    mock_batch = MagicMock()
    mock_batch.status = "completed"
    mock_batch.output_file_id = "file_output_001"

    output_lines = "\n".join(json.dumps(_make_batch_result(rid, text)) for rid, text in responses.items())
    mock_file_content = MagicMock()
    mock_file_content.text = output_lines

    mock_client = MagicMock()
    mock_client.batches.retrieve.return_value = mock_batch
    mock_client.files.content.return_value = mock_file_content

    with (
        patch.object(ef, "RULES_DRAFT_FILE", jsonl_path),
        patch.object(ef, "BATCH_STATE_FILE", batch_state_path),
        patch.object(ef, "REPO_ROOT", tmp_path),
        patch("src.extract_features.openai.OpenAI", return_value=mock_client),
        patch("src.extract_features.git_commit"),
        patch("src.extract_features.subprocess.run"),
    ):
        ef.collect()

    result_rules: list[dict] = []
    with open(jsonl_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                result_rules.append(json.loads(line))
    return result_rules


class TestCollectJSONLOutput:

    def test_valid_safe_replace_written(self, tmp_path):
        """Valid response for a passing rule is written to JSONL correctly."""
        rules = [RULE_REGNAL]
        response = json.dumps({
            "required_features": {
                "all_of": ["HAS_CARDINAL", "PATTERN_REGNAL_NUMERAL_SHAPE"],
                "any_of": [],
                "none_of": ["EXEMPT_IDENTIFIER", "EXEMPT_CODE_SNIPPET"],
            },
            "mutation_class": "safe_replace",
        })
        result = _run_collect_with_mock_responses(rules, {RULE_REGNAL["rule_id"]: response}, tmp_path)
        rule = next(r for r in result if r["rule_id"] == RULE_REGNAL["rule_id"])
        assert rule["mutation_class"] == "safe_replace"
        assert rule["required_features"]["all_of"] == ["HAS_CARDINAL", "PATTERN_REGNAL_NUMERAL_SHAPE"]
        assert "EXEMPT_CODE_SNIPPET" in rule["required_features"]["none_of"]
        assert rule.get("features_error_log") is None

    def test_valid_requires_rewrite_written(self, tmp_path):
        rules = [RULE_PASSIVE]
        response = json.dumps({
            "required_features": {
                "all_of": ["LING_PASSIVE_VOICE"],
                "any_of": ["ZONE_PARAGRAPH", "ZONE_LIST_BULLET"],
                "none_of": ["EXEMPT_QUOTED_CONTENT", "ANCESTOR_BLOCKQUOTE"],
            },
            "mutation_class": "requires_rewrite",
        })
        result = _run_collect_with_mock_responses(rules, {RULE_PASSIVE["rule_id"]: response}, tmp_path)
        rule = next(r for r in result if r["rule_id"] == RULE_PASSIVE["rule_id"])
        assert rule["mutation_class"] == "requires_rewrite"
        assert rule["required_features"]["all_of"] == ["LING_PASSIVE_VOICE"]

    def test_valid_human_review_written(self, tmp_path):
        rules = [RULE_BUREAUCRATIC]
        response = json.dumps({
            "required_features": {
                "all_of": [],
                "any_of": ["LING_PASSIVE_VOICE", "LING_LONG_SENTENCE", "LING_MODAL_VERB"],
                "none_of": ["ANCESTOR_BLOCKQUOTE", "EXEMPT_QUOTED_CONTENT"],
            },
            "mutation_class": "human_review",
        })
        result = _run_collect_with_mock_responses(
            rules, {RULE_BUREAUCRATIC["rule_id"]: response}, tmp_path
        )
        rule = next(r for r in result if r["rule_id"] == RULE_BUREAUCRATIC["rule_id"])
        assert rule["mutation_class"] == "human_review"

    def test_exempt_in_all_of_writes_null(self, tmp_path):
        """EXEMPT_* in all_of → required_features and mutation_class both null."""
        rules = [RULE_DATE]
        bad_response = json.dumps({
            "required_features": {
                "all_of": ["EXEMPT_CODE_SNIPPET"],  # invalid
                "any_of": [],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        })
        result = _run_collect_with_mock_responses(
            rules, {RULE_DATE["rule_id"]: bad_response}, tmp_path
        )
        rule = next(r for r in result if r["rule_id"] == RULE_DATE["rule_id"])
        assert rule["required_features"] is None
        assert rule["mutation_class"] is None
        assert rule.get("features_error_log") is not None

    def test_unknown_feature_writes_null(self, tmp_path):
        """Unknown feature name → required_features and mutation_class both null."""
        rules = [RULE_REGNAL]
        bad_response = json.dumps({
            "required_features": {
                "all_of": ["PATTERN_CROWN_SYMBOL"],  # doesn't exist
                "any_of": [],
                "none_of": [],
            },
            "mutation_class": "safe_replace",
        })
        result = _run_collect_with_mock_responses(
            rules, {RULE_REGNAL["rule_id"]: bad_response}, tmp_path
        )
        rule = next(r for r in result if r["rule_id"] == RULE_REGNAL["rule_id"])
        assert rule["required_features"] is None
        assert rule["mutation_class"] is None
        assert rule.get("features_error_log") is not None

    def test_unknown_mutation_class_writes_null(self, tmp_path):
        """Unknown mutation_class → both fields null."""
        rules = [RULE_DATE]
        bad_response = json.dumps({
            "required_features": {"all_of": ["HAS_DATE"], "any_of": [], "none_of": []},
            "mutation_class": "auto_fix",  # not valid
        })
        result = _run_collect_with_mock_responses(
            rules, {RULE_DATE["rule_id"]: bad_response}, tmp_path
        )
        rule = next(r for r in result if r["rule_id"] == RULE_DATE["rule_id"])
        assert rule["required_features"] is None
        assert rule["mutation_class"] is None

    def test_non_json_output_writes_null(self, tmp_path):
        """Non-JSON LLM output → both fields null."""
        rules = [RULE_PASSIVE]
        bad_response = "I cannot determine the required features for this rule."
        result = _run_collect_with_mock_responses(
            rules, {RULE_PASSIVE["rule_id"]: bad_response}, tmp_path
        )
        rule = next(r for r in result if r["rule_id"] == RULE_PASSIVE["rule_id"])
        assert rule["required_features"] is None
        assert rule["mutation_class"] is None
        assert rule.get("features_error_log") is not None


# ---------------------------------------------------------------------------
# Tests for submit() — dedup and filtering
# ---------------------------------------------------------------------------

class TestSubmitFiltering:

    def _run_submit_capture_requests(
        self,
        rules: list[dict],
        tmp_path: Path,
    ) -> list[dict]:
        """Run submit() and return the batch requests that would be sent."""
        import src.extract_features as ef

        jsonl_path = _make_rules_jsonl(rules, tmp_path)
        batch_state_path = tmp_path / "batch_state.json"
        batch_state_path.write_text("{}")

        submitted_requests: list[dict] = []

        def fake_files_create(file, purpose):
            import io as _io
            content = file.read().decode()
            for line in content.splitlines():
                if line.strip():
                    submitted_requests.append(json.loads(line))
            mock_file = MagicMock()
            mock_file.id = "file_001"
            return mock_file

        mock_batch = MagicMock()
        mock_batch.id = "batch_001"
        mock_client = MagicMock()
        mock_client.files.create.side_effect = fake_files_create
        mock_client.batches.create.return_value = mock_batch

        with (
            patch.object(ef, "RULES_DRAFT_FILE", jsonl_path),
            patch.object(ef, "BATCH_STATE_FILE", batch_state_path),
            patch.object(ef, "REPO_ROOT", tmp_path),
            patch("src.extract_features.openai.OpenAI", return_value=mock_client),
            patch("src.extract_features.git_commit"),
        ):
            ef.submit()

        return submitted_requests

    def test_only_passing_rules_submitted(self, tmp_path):
        """Rules with test_result != 'pass' must not be submitted."""
        rules = [RULE_REGNAL, RULE_FAILING]
        requests = self._run_submit_capture_requests(rules, tmp_path)
        submitted_ids = {r["custom_id"] for r in requests}
        assert RULE_REGNAL["rule_id"] in submitted_ids
        assert RULE_FAILING["rule_id"] not in submitted_ids

    def test_already_annotated_rules_skipped(self, tmp_path):
        """Rules with both fields already populated must be skipped."""
        rules = [RULE_REGNAL, RULE_ALREADY_DONE]
        requests = self._run_submit_capture_requests(rules, tmp_path)
        submitted_ids = {r["custom_id"] for r in requests}
        assert RULE_REGNAL["rule_id"] in submitted_ids
        assert RULE_ALREADY_DONE["rule_id"] not in submitted_ids


# ---------------------------------------------------------------------------
# Tests for build_user_message()
# ---------------------------------------------------------------------------

class TestBuildUserMessage:

    def test_contains_rule_id(self):
        msg = build_user_message(RULE_REGNAL)
        assert RULE_REGNAL["rule_id"] in msg

    def test_contains_rule_summary(self):
        msg = build_user_message(RULE_REGNAL)
        assert RULE_REGNAL["rule_summary"] in msg

    def test_contains_trigger_code(self):
        msg = build_user_message(RULE_DATE)
        assert "2024-01-15" in msg or "r'" in msg

    def test_lookup_list_serialised(self):
        msg = build_user_message(RULE_BUREAUCRATIC)
        assert "pursuant to" in msg
