#!/usr/bin/env python3
"""Phase 6: Publish the validated rulebook as Parquet (manual trigger only)."""

import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
RULES_DRAFT_FILE = REPO_ROOT / "rules_working_draft.jsonl"
PUBLISHED_DIR = REPO_ROOT / "published"
PARQUET_FILE = PUBLISHED_DIR / "rulebook.parquet"
METADATA_FILE = PUBLISHED_DIR / "rulebook_metadata.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


def ensure_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    return [str(val)]


def main() -> None:
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

    if not rules:
        raise SystemExit("No rules found in rules_working_draft.jsonl")

    # Warn about fail rows but continue publishing
    fail_rows = [r for r in rules if r.get("test_result") == "fail"]
    if fail_rows:
        fail_ids = [r.get("rule_id") for r in fail_rows]
        log.warning(
            "%d rule(s) have test_result='fail' and will be included as-is: %s",
            len(fail_rows),
            fail_ids,
        )

    frozen_rows = [r for r in rules if r.get("test_result") == "frozen"]
    if frozen_rows:
        log.warning(
            "%d frozen rule(s) will be included in the published rulebook: %s",
            len(frozen_rows),
            [r.get("rule_id") for r in frozen_rows],
        )

    # Build normalised records
    records = [
        {
            "rule_id": r.get("rule_id"),
            "source_url": r.get("source_url"),
            "source_file": r.get("source_file"),
            "rule_summary": r.get("rule_summary"),
            "rule_detail": r.get("rule_detail"),
            "taxonomy": r.get("taxonomy"),
            "discretionary_flag": bool(r.get("discretionary_flag", False)),
            "method": r.get("method"),
            "requires": ensure_list(r.get("requires")),
            "method_notes": r.get("method_notes"),
            "trigger_code": r.get("trigger_code"),
            "ui_flag": r.get("ui_flag"),
            "test_fire": ensure_list(r.get("test_fire")),
            "test_no_fire": ensure_list(r.get("test_no_fire")),
            "lookup_list": ensure_list(r.get("lookup_list")),
            "test_result": r.get("test_result"),
            "error_log": r.get("error_log"),
            "correction_model": r.get("correction_model"),
            "extracted_at": r.get("extracted_at"),
            "code_generated_at": r.get("code_generated_at"),
            "test_run_at": r.get("test_run_at"),
        }
        for r in rules
    ]

    df = pd.DataFrame(records)

    # Define Parquet schema with correct column types
    schema = pa.schema([
        ("rule_id", pa.string()),
        ("source_url", pa.string()),
        ("source_file", pa.string()),
        ("rule_summary", pa.string()),
        ("rule_detail", pa.string()),
        ("taxonomy", pa.string()),
        ("discretionary_flag", pa.bool_()),
        ("method", pa.string()),
        ("requires", pa.list_(pa.string())),
        ("method_notes", pa.string()),
        ("trigger_code", pa.string()),
        ("ui_flag", pa.string()),
        ("test_fire", pa.list_(pa.string())),
        ("test_no_fire", pa.list_(pa.string())),
        ("lookup_list", pa.list_(pa.string())),
        ("test_result", pa.string()),
        ("error_log", pa.string()),
        ("correction_model", pa.string()),
        ("extracted_at", pa.string()),
        ("code_generated_at", pa.string()),
        ("test_run_at", pa.string()),
    ])

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_table(table, PARQUET_FILE, compression="snappy")

    log.info("Written %d rules to %s", len(records), PARQUET_FILE)

    # Compute metadata
    by_taxonomy: dict[str, int] = {}
    if "taxonomy" in df.columns:
        by_taxonomy = {k: int(v) for k, v in df["taxonomy"].value_counts().items()}

    metadata = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "total_rules": len(records),
        "by_taxonomy": by_taxonomy,
        "fail_count": int((df["test_result"] == "fail").sum()) if "test_result" in df.columns else 0,
        "skip_count": int((df["test_result"] == "skip").sum()) if "test_result" in df.columns else 0,
        "frozen_count": int((df["test_result"] == "frozen").sum()) if "test_result" in df.columns else 0,
        "unassigned_count": int((df["taxonomy"] == "unassigned").sum()) if "taxonomy" in df.columns else 0,
        "sha256": sha256_file(PARQUET_FILE),
    }

    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    git_commit(
        f"Phase 6: publish rulebook ({len(records)} rules)",
        [
            str(PARQUET_FILE.relative_to(REPO_ROOT)),
            str(METADATA_FILE.relative_to(REPO_ROOT)),
        ],
    )

    log.info("Rulebook published: %s", metadata)


if __name__ == "__main__":
    main()
