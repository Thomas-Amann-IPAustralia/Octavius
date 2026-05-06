#!/usr/bin/env python3
"""Phase 5: Correct failed rules via OpenAI Batch API."""

import io
import json
import logging
import os
import re
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
AMENDMENT_LOG_FILE = REPO_ROOT / "amendment_log.json"

MODEL = "gpt-5.4"
BUNDLE_SIZE = 3

CORRECTION_SYSTEM_PROMPT = """You are a code-correction specialist for the Octavius plain-language linter.

Your task: fix failing trigger code for Australian Government Style Manual rules.

For each rule provided, analyse why the trigger code is failing against the test strings and return a corrected version.

## Output Schema

Return a JSON array — one object per rule, no preamble, no markdown fences:

```
[
  {
    "rule_id": "<echo exactly from input — do not modify>",
    "trigger_code": "<corrected code string, or null if uncorrectable>",
    "issue_summary": "Plain-English description of what was wrong.",
    "correction_summary": "Plain-English description of what was changed.",
    "correction_model": "gpt-5.4"
  }
]
```

## Critical instructions

1. Echo `rule_id` EXACTLY from the input — do not modify, shorten, or reformat it.
2. If a rule cannot be fixed, return `trigger_code: null` and explain clearly in `issue_summary` why it cannot be corrected automatically.
3. `correction_model` must always be the literal string `"gpt-5.4"`.
4. Return a JSON array ONLY — no preamble, no explanation, no markdown code fences.
5. Every rule provided must have a corresponding object in the output array.
"""


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
    rules = []
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


def append_amendments(new_amendments: list[dict]) -> None:
    existing: list[dict] = []
    if AMENDMENT_LOG_FILE.exists():
        with open(AMENDMENT_LOG_FILE) as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []
    existing.extend(new_amendments)
    with open(AMENDMENT_LOG_FILE, "w") as f:
        json.dump(existing, f, indent=2)


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


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


# Taxonomies whose failures can be sent for correction
CORRECTABLE_TAXONOMIES = frozenset({"regex", "spacy", "structural", "lookup"})


def submit() -> None:
    """Submit Phase 5 correction batches for failed rules."""
    state = read_batch_state()
    if state and state.get("batch_ids"):
        log.info(
            "batch_state.json has active batches from phase %s. "
            "Previous collect has not completed — this submit is a no-op.",
            state.get("phase"),
        )
        sys.exit(0)

    rules = read_rules()
    # Only correct: failed rules with correctable taxonomies; exclude frozen
    failed_rules = [
        r for r in rules
        if r.get("test_result") == "fail"
        and r.get("taxonomy") in CORRECTABLE_TAXONOMIES
    ]

    if not failed_rules:
        log.info("No failed rules to correct.")
        return

    log.info("Submitting %d failed rules for correction", len(failed_rules))

    client = openai.OpenAI()
    batch_requests: list[dict] = []

    for i in range(0, len(failed_rules), BUNDLE_SIZE):
        bundle = failed_rules[i:i + BUNDLE_SIZE]
        bundle_for_llm = [
            {
                "rule_id": r["rule_id"],
                "rule_summary": r.get("rule_summary", ""),
                "rule_detail": r.get("rule_detail", ""),
                "trigger_code": r.get("trigger_code"),
                "test_fire": r.get("test_fire", []),
                "test_no_fire": r.get("test_no_fire", []),
                "error_log": r.get("error_log"),
            }
            for r in bundle
        ]

        batch_requests.append({
            "custom_id": f"correction-bundle-{i // BUNDLE_SIZE:04d}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "max_completion_tokens": 8192,
                "messages": [
                    {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Fix the following {len(bundle)} failed rules:\n\n"
                            f"{json.dumps(bundle_for_llm, indent=2)}"
                        ),
                    },
                ],
            },
        })

    jsonl_content = "\n".join(json.dumps(r) for r in batch_requests)
    batch_file = client.files.create(
        file=io.BytesIO(jsonl_content.encode()),
        purpose="batch",
    )
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    batch_ids = [batch.id]
    log.info("Created batch %s (%d requests)", batch.id, len(batch_requests))

    write_batch_state({
        "phase": "5",
        "batch_ids": batch_ids,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    git_commit("Phase 5: submit correction batches", ["batch_state.json"])


def collect() -> None:
    """Collect Phase 5 correction results, update JSONL, re-test, freeze uncorrectables."""
    state = read_batch_state()
    if state.get("phase") != "5":
        state_phase = state.get("phase")
        if state_phase is None:
            log.info(
                "No active Phase 5 batch state found. "
                "Either Phase 5 submit has not run yet, or the previous collect already completed."
            )
        else:
            log.info(
                "Active batch belongs to Phase %s, not Phase 5. "
                "Phase 5 submit has not been run in this cycle.",
                state_phase,
            )
        write_github_output("collected", "false")
        sys.exit(0)

    batch_ids: list[str] = state.get("batch_ids", [])
    client = openai.OpenAI()

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

    log.info("All correction batches complete. Collecting results.")

    rules = read_rules()
    rules_by_id: dict[str, dict] = {r["rule_id"]: r for r in rules if "rule_id" in r}

    now = datetime.now(timezone.utc).isoformat()
    amendments: list[dict] = []

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
                log.warning(
                    "Batch result error for custom_id=%s: %s",
                    custom_id,
                    result.get("error") or result.get("response"),
                )
                continue

            text = strip_code_fences(
                result["response"]["body"]["choices"][0]["message"]["content"]
            )

            try:
                returned_objects = json.loads(text)
                if not isinstance(returned_objects, list):
                    returned_objects = [returned_objects]
            except json.JSONDecodeError as e:
                log.error(
                    "Could not parse correction response (custom_id=%s): %s\nText: %.300s",
                    custom_id,
                    e,
                    text,
                )
                continue

            for obj in returned_objects:
                rule_id = obj.get("rule_id")
                if not rule_id:
                    log.error(
                        "Correction response missing rule_id (custom_id=%s): %.120s",
                        custom_id,
                        str(obj),
                    )
                    continue
                if rule_id not in rules_by_id:
                    log.error(
                        "Returned rule_id '%s' not found in draft (custom_id=%s) — skipping",
                        rule_id,
                        custom_id,
                    )
                    continue

                rule = rules_by_id[rule_id]
                rule["trigger_code"] = obj.get("trigger_code")
                rule["code_generated_at"] = now
                rule["correction_model"] = obj.get("correction_model", MODEL)

                amendments.append({
                    "rule_id": rule_id,
                    "amended_at": now,
                    "issue_summary": obj.get("issue_summary", ""),
                    "correction_summary": obj.get("correction_summary", ""),
                    "correction_model": obj.get("correction_model", MODEL),
                })

    # `rules_by_id` values are the same dict instances as in `rules`, so
    # updates above are reflected by writing the original list. Writing
    # `rules` (not `rules_by_id.values()`) preserves original row order and
    # keeps any rows that lack a rule_id (logged, not dropped).
    write_rules(rules)
    append_amendments(amendments)

    write_batch_state({})
    git_commit(
        f"Phase 5: apply corrections ({len(amendments)} rules updated)",
        [
            "batch_state.json",
            str(RULES_DRAFT_FILE.relative_to(REPO_ROOT)),
            str(AMENDMENT_LOG_FILE.relative_to(REPO_ROOT)),
        ],
    )

    log.info(
        "Applied %d corrections. Re-testing via run_tests.py --only-corrected.",
        len(amendments),
    )

    # Re-test corrected rules
    retest = subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "run_tests.py"), "--only-corrected"],
        cwd=REPO_ROOT,
    )
    if retest.returncode != 0:
        log.warning("run_tests.py --only-corrected exited with non-zero code")

    # Mark rules that still fail after correction as frozen
    rules = read_rules()
    frozen_count = 0
    for rule in rules:
        if rule.get("correction_model") and rule.get("test_result") == "fail":
            rule["test_result"] = "frozen"
            frozen_count += 1

    if frozen_count:
        write_rules(rules)
        git_commit(
            f"Phase 5: mark {frozen_count} uncorrectable rule(s) as frozen",
            [str(RULES_DRAFT_FILE.relative_to(REPO_ROOT))],
        )
        log.warning(
            "%d rule(s) could not be corrected and are now frozen (manual intervention required)",
            frozen_count,
        )

    write_github_output("collected", "true")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "collect"):
        print("Usage: correct_rules.py [submit|collect]")
        sys.exit(1)

    if sys.argv[1] == "submit":
        submit()
    else:
        collect()


if __name__ == "__main__":
    main()
