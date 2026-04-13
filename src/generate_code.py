#!/usr/bin/env python3
"""Phase 3: Generate executable trigger code for each rule via OpenAI Batch API."""

import io
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import openai
import tiktoken

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
BATCH_STATE_FILE = REPO_ROOT / "batch_state.json"
RULES_DRAFT_FILE = REPO_ROOT / "rules_working_draft.jsonl"
PROMPTS_DIR = REPO_ROOT / "prompts"

MODEL = "gpt-4o"

VALID_TAXONOMIES = frozenset({
    "regex", "spacy", "structural", "lookup",
    "semantic", "contextual", "discretionary", "multi-modal", "unassigned",
})

# Taxonomies where LLM generates executable trigger_code
CODE_TAXONOMIES = frozenset({"regex", "spacy", "structural", "lookup"})

# Taxonomies where LLM generates a prompt template (no executable code)
TEMPLATE_TAXONOMIES = frozenset({"semantic", "contextual"})

# Taxonomies excluded from LLM submission entirely
SKIP_TAXONOMIES = frozenset({"discretionary", "multi-modal", "unassigned"})

MAX_UNASSIGNED_RATIO_DEFAULT = 0.05
BUNDLE_SIZE = 5

TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    return len(TOKENIZER.encode(str(text)))


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


def github_job_summary(message: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(message + "\n")
    print(message)


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def submit() -> None:
    """Submit Phase 3 batch jobs for code generation."""
    state = read_batch_state()
    if state and state.get("batch_ids"):
        log.info(
            "batch_state.json has active batches from phase %s. "
            "Previous collect has not completed — this submit is a no-op.",
            state.get("phase"),
        )
        sys.exit(0)

    rules = read_rules()
    if not rules:
        raise SystemExit("No rules found in rules_working_draft.jsonl")

    total = len(rules)
    unassigned_count = sum(1 for r in rules if r.get("taxonomy") == "unassigned")
    unassigned_ratio = unassigned_count / total if total > 0 else 0

    max_ratio = float(os.environ.get("MAX_UNASSIGNED_RATIO", MAX_UNASSIGNED_RATIO_DEFAULT))

    if unassigned_ratio > max_ratio:
        msg = (
            f"PIPELINE ABORTED: {unassigned_count} of {total} rules "
            f"({unassigned_ratio:.1%}) have taxonomy 'unassigned', exceeding the "
            f"MAX_UNASSIGNED_RATIO threshold of {max_ratio:.1%}. "
            "This indicates an extraction anomaly in Phase 2. "
            "Manual review required before proceeding."
        )
        github_job_summary(f"## Pipeline Aborted\n\n{msg}")
        raise SystemExit(msg)

    if unassigned_count > 0:
        unassigned_ids = [r["rule_id"] for r in rules if r.get("taxonomy") == "unassigned"]
        log.warning(
            "Excluding %d unassigned rule(s) from code generation: %s",
            unassigned_count,
            unassigned_ids,
        )

    # Validate all taxonomy values against the registry
    unknown_taxonomies: dict[str, str] = {
        r.get("rule_id", "?"): r.get("taxonomy", "")
        for r in rules
        if r.get("taxonomy") not in VALID_TAXONOMIES
    }
    if unknown_taxonomies:
        raise SystemExit(
            f"Unknown taxonomy values found — fix Phase 2 before proceeding:\n"
            + "\n".join(f"  {rid}: {tax}" for rid, tax in unknown_taxonomies.items())
        )

    # Only submit rules that need code and don't yet have it
    submittable = [
        r for r in rules
        if r.get("taxonomy") in (CODE_TAXONOMIES | TEMPLATE_TAXONOMIES)
        and "trigger_code" not in r
    ]

    if not submittable:
        log.info("No rules require code generation.")
        return

    log.info("Submitting %d rules for code generation", len(submittable))

    client = openai.OpenAI()
    all_batch_requests: list[dict] = []

    # Group by taxonomy so the correct prompt file is used per bundle
    by_taxonomy: dict[str, list[dict]] = {}
    for rule in submittable:
        by_taxonomy.setdefault(rule["taxonomy"], []).append(rule)

    for taxonomy, tax_rules in by_taxonomy.items():
        prompt_file = PROMPTS_DIR / f"{taxonomy}.md"
        if not prompt_file.exists():
            raise SystemExit(
                f"Prompt file not found for taxonomy '{taxonomy}': {prompt_file}. "
                "Create the prompt file before running Phase 3."
            )
        system_prompt = prompt_file.read_text(encoding="utf-8")

        for i in range(0, len(tax_rules), BUNDLE_SIZE):
            bundle = tax_rules[i:i + BUNDLE_SIZE]
            bundle_for_llm = [
                {
                    "rule_id": r["rule_id"],
                    "rule_summary": r.get("rule_summary", ""),
                    "rule_detail": r.get("rule_detail", ""),
                    "taxonomy": r["taxonomy"],
                }
                for r in bundle
            ]

            user_message = (
                f"Generate trigger code for the following {len(bundle)} rules.\n\n"
                f"Rules:\n{json.dumps(bundle_for_llm, indent=2)}\n\n"
                "Return a JSON array with one object per rule. "
                "Each object MUST include `rule_id` echoed exactly from input."
            )

            all_batch_requests.append({
                "custom_id": f"{taxonomy}--bundle-{i // BUNDLE_SIZE:04d}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": MODEL,
                    "max_tokens": 8192,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
            })

    # Submit as one or more batches (OpenAI limit: 50k requests per batch)
    BATCH_REQUEST_LIMIT = 10000
    batch_ids: list[str] = []

    for i in range(0, len(all_batch_requests), BATCH_REQUEST_LIMIT):
        chunk = all_batch_requests[i:i + BATCH_REQUEST_LIMIT]
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
        log.info("Created batch %s (%d requests)", batch.id, len(chunk))

    write_batch_state({
        "phase": "3",
        "batch_ids": batch_ids,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    git_commit("Phase 3: submit code generation batches", ["batch_state.json"])
    log.info("Submitted %d batch(es) for %d rules", len(batch_ids), len(submittable))


def collect() -> None:
    """Collect Phase 3 batch results and update rules_working_draft.jsonl."""
    state = read_batch_state()
    if state.get("phase") != "3":
        log.info(
            "batch_state.json phase is '%s', expected '3'. Nothing to collect.",
            state.get("phase"),
        )
        sys.exit(0)

    batch_ids: list[str] = state.get("batch_ids", [])
    client = openai.OpenAI()

    # Poll all batches — exit early if any are not yet complete
    terminal_statuses = {"completed", "failed", "expired", "cancelled"}
    for batch_id in batch_ids:
        batch = client.batches.retrieve(batch_id)
        log.info("Batch %s status: %s", batch_id, batch.status)
        if batch.status not in terminal_statuses:
            log.info("Batch %s not yet complete. Exiting — cron will retry.", batch_id)
            sys.exit(0)

    log.info("All batches complete. Collecting results.")

    rules = read_rules()
    rules_by_id: dict[str, dict] = {r["rule_id"]: r for r in rules if "rule_id" in r}

    now = datetime.now(timezone.utc).isoformat()
    updated_count = 0

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
                    "Could not parse JSON response for custom_id=%s: %s\nText: %.300s",
                    custom_id,
                    e,
                    text,
                )
                continue

            for obj in returned_objects:
                rule_id = obj.get("rule_id")
                if not rule_id:
                    log.error(
                        "Response object missing rule_id (custom_id=%s): %.120s",
                        custom_id,
                        str(obj),
                    )
                    continue
                if rule_id not in rules_by_id:
                    log.error(
                        "Returned rule_id '%s' not found in draft — skipping (custom_id=%s)",
                        rule_id,
                        custom_id,
                    )
                    continue

                trigger_code = obj.get("trigger_code")
                test_fire = obj.get("test_fire", [])
                test_no_fire = obj.get("test_no_fire", [])

                rules_by_id[rule_id].update({
                    "method": obj.get("method"),
                    "requires": obj.get("requires", []),
                    "method_notes": obj.get("method_notes"),
                    "trigger_code": trigger_code,
                    "ui_flag": obj.get("ui_flag"),
                    "test_fire": test_fire,
                    "test_no_fire": test_no_fire,
                    "lookup_list": obj.get("lookup_list"),
                    "code_token_count": count_tokens(trigger_code),
                    "ui_flag_token_count": count_tokens(obj.get("ui_flag")),
                    "test_token_count": sum(
                        count_tokens(s) for s in test_fire + test_no_fire
                    ),
                    "code_generated_at": now,
                })
                updated_count += 1

    # Annotate skipped taxonomies with null trigger_code and skip result
    for rule in rules:
        tax = rule.get("taxonomy")
        if "trigger_code" in rule:
            continue  # already processed
        if tax in ("discretionary", "multi-modal"):
            rule.update({
                "trigger_code": None,
                "test_result": "skip",
                "method_notes": f"taxonomy={tax} — not automatable",
                "code_generated_at": now,
            })
        elif tax == "unassigned":
            rule.update({
                "trigger_code": None,
                "test_result": "skip",
                "method_notes": "Taxonomy unassigned — requires manual review",
                "code_generated_at": now,
            })
        elif tax in ("semantic", "contextual"):
            rule.update({
                "trigger_code": None,
                "test_result": "skip",
                "method_notes": f"taxonomy={tax} — LLM sub-call template only, not executable",
                "code_generated_at": now,
            })

    # Warn about draft rows with no matching LLM response
    for rule in rules:
        if (
            rule.get("taxonomy") in (CODE_TAXONOMIES | TEMPLATE_TAXONOMIES)
            and "trigger_code" not in rule
        ):
            log.warning(
                "No LLM response received for rule_id='%s' (taxonomy=%s) — "
                "left unchanged for manual review.",
                rule.get("rule_id"),
                rule.get("taxonomy"),
            )

    write_rules(rules)
    write_batch_state({})

    git_commit(
        f"Phase 3: collect code generation results ({updated_count} rules updated)",
        [
            "batch_state.json",
            str(RULES_DRAFT_FILE.relative_to(REPO_ROOT)),
        ],
    )
    log.info("Updated %d rules with trigger code", updated_count)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "collect"):
        print("Usage: generate_code.py [submit|collect]")
        sys.exit(1)

    if sys.argv[1] == "submit":
        submit()
    else:
        collect()


if __name__ == "__main__":
    main()
