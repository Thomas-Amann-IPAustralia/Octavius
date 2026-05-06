#!/usr/bin/env python3
"""Phase 3.5: Populate required_features and mutation_class via OpenAI Batch API.

Each passing rule is sent to the LLM with the feature vocabulary as context.
The model returns both fields in a single request (shared reasoning context,
half the cost of two separate batches).
"""

import io
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import openai

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
BATCH_STATE_FILE = REPO_ROOT / "batch_state.json"
RULES_DRAFT_FILE = REPO_ROOT / "rules_working_draft.jsonl"
PROMPT_FILE = REPO_ROOT / "prompts" / "features.md"

MODEL = "gpt-5.4-mini"
PHASE = "3.5"
BATCH_REQUEST_LIMIT = 50_000

VALID_MUTATION_CLASSES = frozenset({"safe_replace", "requires_rewrite", "human_review"})


def _import_vocab():
    """Import vocabulary helpers at call time (avoids adding sys.path at module level)."""
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    from logic.features.vocabulary import validate_feature, EXEMPT_FEATURES
    return validate_feature, EXEMPT_FEATURES


def write_github_output(key: str, value: str) -> None:
    """Write a key=value pair to GITHUB_OUTPUT when running inside GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


def read_batch_state() -> dict:
    if BATCH_STATE_FILE.exists():
        with open(BATCH_STATE_FILE) as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    return {}


def write_batch_state(state: dict) -> None:
    with open(BATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def read_rules() -> list[dict]:
    rules: list[dict] = []
    if RULES_DRAFT_FILE.exists():
        with open(RULES_DRAFT_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rules.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("Could not parse JSONL line: %s", line[:100])
    return rules


def write_rules(rules: list[dict]) -> None:
    with open(RULES_DRAFT_FILE, "w") as f:
        for rule in rules:
            f.write(json.dumps(rule) + "\n")


def git_commit(message: str, files: list[str]) -> None:
    subprocess.run(["git", "config", "user.name", "OctaviusBot"], cwd=REPO_ROOT)
    subprocess.run(
        ["git", "config", "user.email", "octavius-bot@users.noreply.github.com"],
        cwd=REPO_ROOT,
    )
    subprocess.run(["git", "add", "--"] + files, check=True, cwd=REPO_ROOT)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
    if result.returncode == 0:
        log.info("Nothing to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=REPO_ROOT)


def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise SystemExit(f"Prompt file not found: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def build_user_message(rule: dict) -> str:
    lookup_list = rule.get("lookup_list") or []
    test_fire = rule.get("test_fire") or []
    test_no_fire = rule.get("test_no_fire") or []
    trigger_code = rule.get("trigger_code") or "(none)"
    lines = [
        f"rule_id: {rule.get('rule_id', '')}",
        f"rule_summary: {rule.get('rule_summary', '')}",
        f"rule_detail: {rule.get('rule_detail', '')}",
        f"taxonomy: {rule.get('taxonomy', '')}",
        f"source_url: {rule.get('source_url', '')}",
        f"ui_flag: {rule.get('ui_flag', '')}",
        f"lookup_list: {json.dumps(lookup_list)}",
        f"trigger_code:\n{trigger_code}",
        f"test_fire: {json.dumps(test_fire)}",
        f"test_no_fire: {json.dumps(test_no_fire)}",
    ]
    return "\n".join(lines)


def validate_response(
    data: dict,
    validate_feature,
    exempt_features: frozenset,
) -> tuple[dict | None, str | None]:
    """Validate a parsed LLM response dict.

    Returns (validated_data, error_message). On success error_message is None.
    On failure, validated_data is None and error_message describes the problem.
    """
    # Check top-level keys
    if "required_features" not in data or "mutation_class" not in data:
        missing = [k for k in ("required_features", "mutation_class") if k not in data]
        return None, f"Missing top-level keys: {missing}"

    # Validate mutation_class
    mc = data["mutation_class"]
    if mc not in VALID_MUTATION_CLASSES:
        return None, f"Unknown mutation_class: {mc!r}. Must be one of {sorted(VALID_MUTATION_CLASSES)}"

    rf = data["required_features"]
    if not isinstance(rf, dict):
        return None, f"required_features must be an object, got {type(rf).__name__}"

    all_of = rf.get("all_of") or []
    any_of = rf.get("any_of") or []
    none_of = rf.get("none_of") or []

    if not isinstance(all_of, list) or not isinstance(any_of, list) or not isinstance(none_of, list):
        return None, "required_features slots (all_of, any_of, none_of) must be arrays"

    # Validate feature names and EXEMPT_* placement
    for slot_name, slot in (("all_of", all_of), ("any_of", any_of), ("none_of", none_of)):
        for feature in slot:
            try:
                validate_feature(feature)
            except ValueError as exc:
                return None, f"In {slot_name}: {exc}"
            if feature in exempt_features and slot_name in ("all_of", "any_of"):
                return None, (
                    f"EXEMPT_* feature {feature!r} appears in {slot_name!r}. "
                    "EXEMPT_* features may ONLY appear in none_of."
                )

    validated = {
        "required_features": {
            "all_of": [str(f) for f in all_of],
            "any_of": [str(f) for f in any_of],
            "none_of": [str(f) for f in none_of],
        },
        "mutation_class": mc,
    }
    return validated, None


def submit() -> None:
    """Submit Phase 3.5 batch jobs for feature and mutation_class authoring."""
    state = read_batch_state()
    if state and state.get("batch_ids"):
        log.info(
            "batch_state.json has active batches from phase %s. "
            "Previous collect has not completed — this submit is a no-op.",
            state.get("phase"),
        )
        sys.exit(0)

    rules = read_rules()

    # Only process passing rules that have not yet been annotated
    in_flight_ids: set[str] = set(state.get("processed_rule_ids", []))
    pending = [
        r for r in rules
        if r.get("test_result") == "pass"
        and r.get("rule_id") not in in_flight_ids
        and not (r.get("required_features") is not None and r.get("mutation_class") is not None)
    ]

    if not pending:
        log.info(
            "No passing rules need feature annotation. "
            "(%d rules already annotated, %d in flight)",
            sum(1 for r in rules if r.get("required_features") is not None and r.get("mutation_class") is not None),
            len(in_flight_ids),
        )
        return

    log.info("Preparing to submit %d rules for feature annotation", len(pending))

    system_prompt = load_prompt_template()
    client = openai.OpenAI()

    batch_requests: list[dict] = []
    rule_ids_submitted: list[str] = []

    for rule in pending:
        rule_id = rule["rule_id"]
        batch_requests.append({
            "custom_id": rule_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "max_completion_tokens": 1024,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": build_user_message(rule)},
                ],
            },
        })
        rule_ids_submitted.append(rule_id)

    # Submit in chunks if needed (batch API limit is 50k requests per batch)
    batch_ids: list[str] = []
    for i in range(0, len(batch_requests), BATCH_REQUEST_LIMIT):
        chunk = batch_requests[i:i + BATCH_REQUEST_LIMIT]
        log.info(
            "Submitting batch %d/%d (%d requests)",
            i // BATCH_REQUEST_LIMIT + 1,
            (len(batch_requests) + BATCH_REQUEST_LIMIT - 1) // BATCH_REQUEST_LIMIT,
            len(chunk),
        )
        jsonl_content = "\n".join(json.dumps(r) for r in chunk)
        batch_file = client.files.create(
            file=io.BytesIO(jsonl_content.encode()),
            purpose="batch",
        )
        batch = client.batches.create(
            input_file_id=batch_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        batch_ids.append(batch.id)
        log.info("Created batch: %s", batch.id)

    write_batch_state({
        "phase": PHASE,
        "batch_ids": batch_ids,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processed_rule_ids": sorted(set(in_flight_ids) | set(rule_ids_submitted)),
    })
    git_commit("Phase 3.5: submit feature-authoring batches", ["batch_state.json"])

    log.info("Submitted %d batch(es) for %d rules", len(batch_ids), len(pending))


def collect() -> None:
    """Collect Phase 3.5 results and write required_features + mutation_class back to JSONL."""
    state = read_batch_state()
    if state.get("phase") != PHASE:
        state_phase = state.get("phase")
        if state_phase is None:
            log.info(
                "No active Phase %s batch state found. "
                "Either Phase %s submit has not run yet, or the previous collect already completed.",
                PHASE,
                PHASE,
            )
        else:
            log.info(
                "Active batch belongs to Phase %s, not Phase %s. "
                "Phase %s submit has not been run in this cycle.",
                state_phase,
                PHASE,
                PHASE,
            )
        write_github_output("collected", "false")
        sys.exit(0)

    batch_ids: list[str] = state.get("batch_ids", [])
    if not batch_ids:
        raise SystemExit("No batch IDs found in batch_state.json")

    client = openai.OpenAI()
    validate_feature, exempt_features = _import_vocab()

    # Poll all batches — exit early if any are not yet complete
    terminal_statuses = {"completed", "failed", "expired", "cancelled"}
    for batch_id in batch_ids:
        batch = client.batches.retrieve(batch_id)
        log.info("Batch %s status: %s", batch_id, batch.status)
        if batch.status not in terminal_statuses:
            log.info(
                "Batch %s not yet complete (status: %s). Exiting — cron will retry.",
                batch_id,
                batch.status,
            )
            write_github_output("collected", "false")
            sys.exit(0)

    log.info("All batches complete. Collecting feature-authoring results.")

    rules = read_rules()
    rules_by_id: dict[str, dict] = {r["rule_id"]: r for r in rules if "rule_id" in r}

    success_count = 0
    failure_count = 0

    for batch_id in batch_ids:
        batch = client.batches.retrieve(batch_id)
        if batch.status != "completed" or not batch.output_file_id:
            log.warning("Batch %s ended with status %s — skipping", batch_id, batch.status)
            continue

        file_content = client.files.content(batch.output_file_id).text
        for raw_line in file_content.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            result = json.loads(raw_line)
            custom_id = result.get("custom_id", "")

            if result.get("error") or result.get("response", {}).get("status_code") != 200:
                log.error(
                    "Batch result error for rule_id=%s: %s",
                    custom_id,
                    result.get("error") or result.get("response"),
                )
                if custom_id in rules_by_id:
                    rules_by_id[custom_id]["required_features"] = None
                    rules_by_id[custom_id]["mutation_class"] = None
                    rules_by_id[custom_id]["features_error_log"] = "API error in batch response"
                failure_count += 1
                continue

            text = result["response"]["body"]["choices"][0]["message"]["content"].strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                import re
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            text = text.strip()

            rule_id = custom_id
            if rule_id not in rules_by_id:
                log.error("Returned rule_id %r not found in draft — skipping", rule_id)
                failure_count += 1
                continue

            rule = rules_by_id[rule_id]

            # Parse JSON
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                log.error(
                    "Non-JSON response for rule_id=%s: %s\nText: %.300s",
                    rule_id,
                    exc,
                    text,
                )
                rule["required_features"] = None
                rule["mutation_class"] = None
                rule["features_error_log"] = f"JSON parse error: {exc}"
                failure_count += 1
                continue

            # Validate
            validated, error_msg = validate_response(data, validate_feature, exempt_features)
            if error_msg:
                log.error("Validation failure for rule_id=%s: %s", rule_id, error_msg)
                rule["required_features"] = None
                rule["mutation_class"] = None
                rule["features_error_log"] = error_msg
                failure_count += 1
            else:
                rule["required_features"] = validated["required_features"]
                rule["mutation_class"] = validated["mutation_class"]
                rule["features_error_log"] = None
                success_count += 1

    write_rules(rules)

    write_batch_state({})

    git_commit(
        f"Phase 3.5: annotate features ({success_count} succeeded, {failure_count} failed)",
        [
            "batch_state.json",
            str(RULES_DRAFT_FILE.relative_to(REPO_ROOT)),
        ],
    )

    log.info(
        "Feature annotation complete: %d succeeded, %d failed",
        success_count,
        failure_count,
    )

    write_github_output("collected", "true")

    # Emit summary statistics
    rules = read_rules()
    pass_rules = [r for r in rules if r.get("test_result") == "pass"]
    annotated = [r for r in pass_rules if r.get("required_features") is not None]
    mc_dist: dict[str, int] = {}
    for r in annotated:
        mc = r.get("mutation_class") or "null"
        mc_dist[mc] = mc_dist.get(mc, 0) + 1

    log.info(
        "Pass rules: %d total, %d annotated (%.0f%%)",
        len(pass_rules),
        len(annotated),
        100.0 * len(annotated) / len(pass_rules) if pass_rules else 0,
    )
    log.info("mutation_class distribution: %s", mc_dist)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "collect"):
        print("Usage: extract_features.py [submit|collect]")
        sys.exit(1)

    if sys.argv[1] == "submit":
        submit()
    else:
        collect()


if __name__ == "__main__":
    main()
