#!/usr/bin/env python3
"""Phase 2: Extract style rules from markdown content via OpenAI Batch API."""

import io
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import openai

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
CONTENT_DIR = REPO_ROOT / "content"
BATCH_STATE_FILE = REPO_ROOT / "batch_state.json"
RULES_DRAFT_FILE = REPO_ROOT / "rules_working_draft.jsonl"
CONTENT_MANIFEST_FILE = REPO_ROOT / "content_manifest.json"

MODEL = "gpt-5.4-mini"

# Taxonomy Registry — canonical list included verbatim in extraction prompts
TAXONOMY_REGISTRY_TABLE = """
| Taxonomy | Generates trigger_code? | Notes |
|---|---|---|
| `regex` | Yes | Python-compatible regex via `re` module |
| `spacy` | Yes | spaCy `Matcher` or `DependencyMatcher` pattern |
| `structural` | Yes | AST or document-structure check |
| `lookup` | Yes | Checks against a word/phrase list in `lookup_list` |
| `semantic` | No — LLM sub-call template only | Not executable; documents intent for future implementation |
| `contextual` | No — LLM sub-call template only | Not executable; documents intent for future implementation |
| `discretionary` | No — skipped | Rule is advisory; `trigger_code: null`, `test_result: skip` |
| `multi-modal` | No — skipped | Requires visual/layout analysis; `trigger_code: null`, `test_result: skip` |
| `unassigned` | No — excluded from Phase 3 | Extraction anomaly; use ONLY if genuinely cannot assign a taxonomy |
"""

EXTRACTION_SYSTEM_PROMPT = f"""You are a style-rule extraction specialist for the Australian Government Style Manual.

Your task: read the provided markdown content and identify every discrete, enforceable style rule. Return each rule as a separate JSON object on its own line (JSONL format).

## Taxonomy Registry (MANDATORY — use ONLY these exact strings for `taxonomy`)

{TAXONOMY_REGISTRY_TABLE}

## Output Schema (one JSON object per line, no preamble, no markdown fences)

```
{{"rule_id": "<slug>", "source_url": "<url>", "source_file": "<relative path>", "rule_summary": "<one sentence>", "rule_detail": "<full text>", "taxonomy": "<from registry>", "discretionary_flag": <true|false>, "extracted_at": "<ISO 8601>"}}
```

## Field specifications

- `rule_id`: URL path slug + zero-padded sequential index. Replace `/` with `--`, normalise to lowercase, use `-` as separator. No `/` characters. Example: page `grammar-punctuation/punctuation/apostrophes` → IDs `grammar-punctuation--punctuation--apostrophes-001`, `grammar-punctuation--punctuation--apostrophes-002`, etc.
- `source_url`: The originating page URL (provided in the user message).
- `source_file`: Relative path to the markdown source file (provided in the user message).
- `rule_summary`: One sentence, plain English. Start with a verb. E.g. "Use an apostrophe to indicate possession."
- `rule_detail`: The exact text of the rule as found in the source, including any qualifications or exceptions.
- `taxonomy`: MUST be one of the values in the Taxonomy Registry. Default to `unassigned` ONLY if you genuinely cannot determine a valid taxonomy after careful consideration.
- `discretionary_flag`: `true` if the source uses language like "you may", "it is acceptable to", "consider", "can be used", "is optional". Otherwise `false`.
- `extracted_at`: Current ISO 8601 timestamp.

## Critical rules

1. ONE RULE PER LINE. Never merge related rules into one entry.
2. SPLIT compound rules: "use apostrophe for possession but not for plurals" → two separate entries.
3. If a page contains no extractable rules, return exactly: {{"no_rules": true, "source_url": "<url>"}}
4. Return ONLY the JSONL lines. No preamble, no explanation, no markdown code fences.
"""


def read_batch_state() -> dict:
    if BATCH_STATE_FILE.exists():
        with (BATCH_STATE_FILE) as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    return {}


def write_batch_state(state: dict) -> None:
    with open(BATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def extracted_source_files() -> set[str]:
    """Return the set of ``source_file`` paths already recorded in the draft.

    ``rules_working_draft.jsonl`` is the persistent record of completed
    extraction. ``batch_state.json`` is cleared between cycles, so we cannot
    rely on it alone to avoid re-submitting already-processed pages. Any
    markdown file that has at least one rule in the draft is considered
    already extracted and should be skipped on subsequent submits.
    """
    seen: set[str] = set()
    if not RULES_DRAFT_FILE.exists():
        return seen
    with open(RULES_DRAFT_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            source_file = obj.get("source_file")
            if source_file:
                seen.add(source_file)
    return seen


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


def submit() -> None:
    """Submit Phase 2 batch jobs for rule extraction."""
    # Verify content_manifest.json exists
    if not CONTENT_MANIFEST_FILE.exists():
        raise SystemExit(
            "Phase 2 cannot proceed: content_manifest.json not found. "
            "Phase 1 may not have completed successfully."
        )

    # Guard against submitting over an active batch
    state = read_batch_state()
    if state and state.get("batch_ids"):
        log.info(
            "batch_state.json has active batches from phase %s. "
            "Previous collect has not completed — this submit is a no-op.",
            state.get("phase"),
        )
        sys.exit(0)

    # Persistent dedup source: any markdown file that has already produced
    # rules in rules_working_draft.jsonl has been extracted and must not be
    # resubmitted. `in_flight` covers the narrower case of a submit that was
    # retried before its own collect completed.
    already_extracted = extracted_source_files()
    in_flight: set[str] = set(state.get("processed_files", []))
    skip_set = already_extracted | in_flight

    # Find all markdown files not yet processed
    all_files = sorted(
        p for p in CONTENT_DIR.rglob("*.md")
        if str(p.relative_to(REPO_ROOT)) not in skip_set
    )

    if not all_files:
        log.info(
            "No new files to process. %d file(s) already extracted; "
            "%d file(s) currently in flight.",
            len(already_extracted), len(in_flight),
        )
        return

    log.info(
        "Preparing to submit %d files for extraction "
        "(skipping %d already-extracted, %d in-flight)",
        len(all_files), len(already_extracted), len(in_flight),
    )

    client = openai.OpenAI()

    # Build one batch request per markdown file
    batch_requests: list[dict] = []
    file_custom_ids: list[str] = []

    for md_file in all_files:
        rel_path = str(md_file.relative_to(REPO_ROOT))
        content = md_file.read_text(encoding="utf-8")

        # Derive source URL from file path
        path_part = md_file.relative_to(CONTENT_DIR).with_suffix("").as_posix()
        source_url = f"https://www.stylemanual.gov.au/{path_part}"

        user_message = (
            f"Source file: {rel_path}\n"
            f"Source URL: {source_url}\n\n"
            f"--- CONTENT ---\n{content}\n--- END CONTENT ---\n\n"
            "Extract all discrete style rules from the above content. "
            "Return one JSON object per line."
        )

        batch_requests.append({
            "custom_id": rel_path,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "max_completion_tokens": 4096,
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
        })
        file_custom_ids.append(rel_path)

    # Submit in batches of up to 500 requests each
    BATCH_REQUEST_LIMIT = 500
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

    # Write batch_state.json. `processed_files` records the paths that are
    # currently in flight so a retried submit (before collect) does not
    # double-submit the same files. Persistent dedup across cycles is handled
    # by extracted_source_files() reading from rules_working_draft.jsonl.
    new_state = {
        "phase": "2",
        "batch_ids": batch_ids,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processed_files": sorted(in_flight | set(file_custom_ids)),
    }
    write_batch_state(new_state)
    git_commit("Phase 2: submit extraction batches", ["batch_state.json"])

    log.info("Submitted %d batch(es) for %d files", len(batch_ids), len(all_files))


def collect() -> None:
    """Collect Phase 2 batch results and append to rules_working_draft.jsonl."""
    state = read_batch_state()
    if state.get("phase") != "2":
        log.info(
            "batch_state.json phase is '%s', expected '2'. Nothing to collect.",
            state.get("phase"),
        )
        sys.exit(0)

    batch_ids: list[str] = state.get("batch_ids", [])
    if not batch_ids:
        raise SystemExit("No batch IDs found in batch_state.json")

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

    # Load existing rule_ids to prevent duplicates
    existing_rule_ids: set[str] = set()
    if RULES_DRAFT_FILE.exists():
        with open(RULES_DRAFT_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        if "rule_id" in obj:
                            existing_rule_ids.add(obj["rule_id"])
                    except json.JSONDecodeError:
                        pass

    new_rules: list[dict] = []

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

            text = result["response"]["body"]["choices"][0]["message"]["content"].strip()
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    log.warning(
                        "Could not parse line as JSON (custom_id=%s): %s",
                        custom_id,
                        line[:120],
                    )
                    continue

                if obj.get("no_rules"):
                    log.info("No rules on page: %s", obj.get("source_url"))
                    continue

                rule_id = obj.get("rule_id")
                if not rule_id:
                    log.warning(
                        "Missing rule_id in extracted object (custom_id=%s): %s",
                        custom_id,
                        str(obj)[:120],
                    )
                    continue

                if rule_id in existing_rule_ids:
                    log.debug("Skipping duplicate rule_id: %s", rule_id)
                    continue

                new_rules.append(obj)
                existing_rule_ids.add(rule_id)

    # Append to JSONL
    with open(RULES_DRAFT_FILE, "a") as f:
        for rule in new_rules:
            f.write(json.dumps(rule) + "\n")

    log.info("Appended %d new rules to %s", len(new_rules), RULES_DRAFT_FILE.name)

    # Clear batch_state
    write_batch_state({})

    git_commit(
        f"Phase 2: collect {len(new_rules)} extracted rules",
        [
            "batch_state.json",
            str(RULES_DRAFT_FILE.relative_to(REPO_ROOT)),
        ],
    )


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "collect"):
        print("Usage: extract_rules.py [submit|collect]")
        sys.exit(1)

    if sys.argv[1] == "submit":
        submit()
    else:
        collect()


if __name__ == "__main__":
    main()
