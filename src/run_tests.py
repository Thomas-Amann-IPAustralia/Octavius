#!/usr/bin/env python3
"""Phase 4: Run tests for each rule's trigger code against test strings."""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
RULES_DRAFT_FILE = REPO_ROOT / "rules_working_draft.jsonl"


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


def github_job_summary(content: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(content + "\n")
    print(content)


# ---------------------------------------------------------------------------
# Per-taxonomy test functions
# ---------------------------------------------------------------------------

def test_regex_rule(rule: dict) -> tuple[bool, Optional[str]]:
    """Test a regex-taxonomy rule against its test strings."""
    trigger_code = rule.get("trigger_code")
    if not trigger_code:
        return False, "No trigger_code"

    try:
        pattern = re.compile(trigger_code, re.IGNORECASE)
    except re.error as e:
        return False, f"Invalid regex: {e}"

    for text in rule.get("test_fire", []):
        if not pattern.search(text):
            return False, f"SHOULD fire but didn't: {text!r}"

    for text in rule.get("test_no_fire", []):
        if pattern.search(text):
            return False, f"SHOULD NOT fire but did: {text!r}"

    return True, None


def test_spacy_rule(rule: dict, nlp) -> tuple[bool, Optional[str]]:
    """Test a spacy-taxonomy rule.

    trigger_code must define a function ``check_rule(doc)`` that returns a
    truthy value when the rule fires and a falsy value when it does not.
    """
    trigger_code = rule.get("trigger_code")
    if not trigger_code:
        return False, "No trigger_code"

    namespace: dict = {"nlp": nlp}
    try:
        exec(trigger_code, namespace)  # noqa: S102
    except Exception as e:
        return False, f"Error compiling trigger_code: {e}"

    check_fn = namespace.get("check_rule")
    if not callable(check_fn):
        return False, "trigger_code must define a callable check_rule(doc)"

    for text in rule.get("test_fire", []):
        doc = nlp(text)
        try:
            result = check_fn(doc)
            if not result:
                return False, f"SHOULD fire but didn't: {text!r}"
        except Exception as e:
            return False, f"Error running check_rule on fire test {text!r}: {e}"

    for text in rule.get("test_no_fire", []):
        doc = nlp(text)
        try:
            result = check_fn(doc)
            if result:
                return False, f"SHOULD NOT fire but did: {text!r}"
        except Exception as e:
            return False, f"Error running check_rule on no-fire test {text!r}: {e}"

    return True, None


def test_lookup_rule(rule: dict) -> tuple[bool, Optional[str]]:
    """Test a lookup-taxonomy rule.

    trigger_code must define ``check_rule(text, lookup_list)`` that returns a
    truthy value when the text contains a word from the lookup list.
    """
    trigger_code = rule.get("trigger_code")
    lookup_list = rule.get("lookup_list") or []
    if not trigger_code:
        return False, "No trigger_code"

    namespace: dict = {"lookup_list": lookup_list}
    try:
        exec(trigger_code, namespace)  # noqa: S102
    except Exception as e:
        return False, f"Error compiling trigger_code: {e}"

    check_fn = namespace.get("check_rule")
    if not callable(check_fn):
        return False, "trigger_code must define a callable check_rule(text, lookup_list)"

    for text in rule.get("test_fire", []):
        try:
            if not check_fn(text, lookup_list):
                return False, f"SHOULD fire but didn't: {text!r}"
        except Exception as e:
            return False, f"Error in check_rule (fire) for {text!r}: {e}"

    for text in rule.get("test_no_fire", []):
        try:
            if check_fn(text, lookup_list):
                return False, f"SHOULD NOT fire but did: {text!r}"
        except Exception as e:
            return False, f"Error in check_rule (no-fire) for {text!r}: {e}"

    return True, None


def test_structural_rule(rule: dict) -> tuple[bool, Optional[str]]:
    """Test a structural-taxonomy rule.

    trigger_code must define ``check_rule(text)`` that returns a truthy value
    when the structural rule fires.
    """
    trigger_code = rule.get("trigger_code")
    if not trigger_code:
        return False, "No trigger_code"

    namespace: dict = {}
    try:
        exec(trigger_code, namespace)  # noqa: S102
    except Exception as e:
        return False, f"Error compiling trigger_code: {e}"

    check_fn = namespace.get("check_rule")
    if not callable(check_fn):
        return False, "trigger_code must define a callable check_rule(text)"

    for text in rule.get("test_fire", []):
        try:
            if not check_fn(text):
                return False, f"SHOULD fire but didn't: {text!r}"
        except Exception as e:
            return False, f"Error in check_rule (fire) for {text!r}: {e}"

    for text in rule.get("test_no_fire", []):
        try:
            if check_fn(text):
                return False, f"SHOULD NOT fire but did: {text!r}"
        except Exception as e:
            return False, f"Error in check_rule (no-fire) for {text!r}: {e}"

    return True, None


def run_test(rule: dict, nlp=None) -> tuple[str, Optional[str]]:
    """Run tests for a single rule. Returns (test_result, error_log)."""
    trigger_code = rule.get("trigger_code")
    taxonomy = rule.get("taxonomy")

    # Frozen rules stay frozen until manual intervention
    if rule.get("test_result") == "frozen":
        return "frozen", rule.get("error_log")

    # Null trigger_code = skip
    if trigger_code is None:
        return "skip", None

    if taxonomy == "regex":
        passed, error = test_regex_rule(rule)
    elif taxonomy == "spacy":
        if nlp is None:
            return "skip", "spaCy model not loaded"
        passed, error = test_spacy_rule(rule, nlp)
    elif taxonomy == "lookup":
        passed, error = test_lookup_rule(rule)
    elif taxonomy == "structural":
        passed, error = test_structural_rule(rule)
    else:
        return "skip", None

    return ("pass" if passed else "fail"), error


def main() -> None:
    only_corrected = "--only-corrected" in sys.argv

    rules = read_rules()

    # Load spaCy only if we have spaCy rules to test
    nlp = None
    needs_spacy = any(
        r.get("taxonomy") == "spacy" and r.get("trigger_code") for r in rules
    )
    if needs_spacy:
        try:
            import spacy  # noqa: PLC0415

            nlp = spacy.load("en_core_web_sm")
            log.info("Loaded spaCy model en_core_web_sm")
        except Exception as e:
            log.warning(
                "Could not load spaCy model: %s — spaCy rules will be skipped", e
            )

    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = {"pass": 0, "fail": 0, "skip": 0, "frozen": 0}
    failures: list[dict] = []
    unassigned_rule_ids: list[str] = []

    for rule in rules:
        rule_id = rule.get("rule_id", "unknown")

        if rule.get("taxonomy") == "unassigned":
            unassigned_rule_ids.append(rule_id)

        # In --only-corrected mode, skip rules that don't need re-testing
        if only_corrected:
            if not (
                rule.get("correction_model")
                and rule.get("test_result") not in ("pass", "frozen")
            ):
                continue

        result, error = run_test(rule, nlp)
        rule["test_result"] = result
        rule["test_run_at"] = now
        rule["error_log"] = error
        counts[result] += 1

        if result == "fail":
            failures.append({
                "rule_id": rule_id,
                "taxonomy": rule.get("taxonomy"),
                "error_log": error,
            })

    write_rules(rules)

    # Generate test report
    total = sum(counts.values())
    report_lines = [
        "# Octavius Rulebook — Test Report",
        "",
        f"**Run at:** {now}",
        f"**Mode:** {'only-corrected' if only_corrected else 'all'}",
        "",
        "## Summary",
        "",
        "| Result | Count |",
        "|---|---|",
        f"| Pass | {counts['pass']} |",
        f"| Fail | {counts['fail']} |",
        f"| Skip | {counts['skip']} |",
        f"| Frozen | {counts['frozen']} |",
        f"| **Total** | **{total}** |",
        "",
    ]

    if unassigned_rule_ids:
        report_lines += [
            "## ⚠️ Unassigned Taxonomy Warning",
            "",
            f"The following {len(unassigned_rule_ids)} rule(s) have `taxonomy: unassigned` "
            "and require manual review:",
            "",
            *[f"- `{rid}`" for rid in unassigned_rule_ids],
            "",
        ]

    if failures:
        report_lines += [
            f"## Failures ({len(failures)})",
            "",
            "| rule_id | taxonomy | error |",
            "|---|---|---|",
        ]
        for f_item in failures:
            err = (f_item["error_log"] or "")[:120].replace("|", "\\|")
            report_lines.append(
                f"| `{f_item['rule_id']}` | {f_item['taxonomy']} | {err} |"
            )
        report_lines.append("")

    report = "\n".join(report_lines)

    # Write test_report.md
    report_file = REPO_ROOT / "test_report.md"
    report_file.write_text(report, encoding="utf-8")

    # Publish as GitHub Actions Job Summary
    github_job_summary(report)

    # Commit updated JSONL (test_report.md is ephemeral — not committed)
    git_commit(
        f"Phase 4: test results — {counts['pass']} pass, "
        f"{counts['fail']} fail, {counts['skip']} skip, {counts['frozen']} frozen",
        [str(RULES_DRAFT_FILE.relative_to(REPO_ROOT))],
    )

    log.info("Tests complete: %s", counts)


if __name__ == "__main__":
    main()
