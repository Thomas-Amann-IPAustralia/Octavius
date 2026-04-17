"""Load validated rules from published/rulebook.parquet into the engine."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

_RULEBOOK_PATH = Path(__file__).parent.parent / "published" / "rulebook.parquet"


def _make_lookup_check(lookup_list: list[str]) -> Callable:
    patterns: list[re.Pattern] = []
    for term in lookup_list:
        try:
            patterns.append(re.compile(r"\b" + re.escape(term.lower()) + r"\b"))
        except re.error:
            pass

    def check(doc) -> list[dict[str, Any]]:
        text = doc.text
        text_lower = text.lower()
        findings: list[dict[str, Any]] = []
        for pat in patterns:
            for m in pat.finditer(text_lower):
                findings.append({"start_char": m.start(), "end_char": m.end()})
        return findings

    return check


def _make_regex_check(pattern_str: str) -> Callable | None:
    try:
        pat = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
    except re.error:
        return None

    def check(doc) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for m in pat.finditer(doc.text):
            if m.end() > m.start():
                findings.append({"start_char": m.start(), "end_char": m.end()})
        return findings

    return check


def _make_structural_check(trigger_code: str) -> Callable | None:
    namespace: dict = {}
    try:
        exec(compile(trigger_code, "<rulebook>", "exec"), namespace)
    except Exception:
        return None

    check_fn = namespace.get("check_rule")
    if not callable(check_fn):
        return None

    def check(doc) -> list[dict[str, Any]]:
        text = doc.text
        if not text.strip():
            return []
        try:
            result = check_fn(text)
        except Exception:
            return []
        if not result:
            return []
        findings: list[dict[str, Any]] = []
        for item in result:
            if isinstance(item, str) and len(item) > 1:
                idx = text.find(item)
                if idx >= 0:
                    findings.append({"start_char": idx, "end_char": idx + len(item)})
                else:
                    # Descriptive message with no verbatim match — document-level finding
                    findings.append({"start_char": 0, "end_char": min(len(text), 100)})
            else:
                findings.append({"start_char": 0, "end_char": min(len(text), 100)})
        return findings

    return check


def _derive_category(source_file: str) -> str:
    parts = source_file.strip("/").split("/")
    if len(parts) >= 2:
        return parts[1].replace("-", " ").title()
    return "General"


def load_rulebook_rules() -> list[dict]:
    """Return Rule dicts for all passing rules in published/rulebook.parquet.

    Returns an empty list if the parquet file is absent so the app still
    starts in development environments without the published artefact.
    """
    if not _RULEBOOK_PATH.exists():
        return []

    import pandas as pd  # deferred — avoids import cost if parquet is absent

    df = pd.read_parquet(_RULEBOOK_PATH)
    passing = df[df["test_result"] == "pass"]

    rules: list[dict] = []
    for _, row in passing.iterrows():
        taxonomy = str(row.get("taxonomy") or "")
        raw_lookup = row.get("lookup_list")
        lookup_list: list[str] = list(raw_lookup) if raw_lookup is not None and len(raw_lookup) > 0 else []
        trigger_code = str(row.get("trigger_code") or "").strip()

        if taxonomy == "lookup":
            if not lookup_list:
                continue
            check_fn: Callable | None = _make_lookup_check(lookup_list)
        elif taxonomy == "regex":
            if not trigger_code:
                continue
            check_fn = _make_regex_check(trigger_code)
        elif taxonomy == "structural":
            if not trigger_code:
                continue
            check_fn = _make_structural_check(trigger_code)
        else:
            continue

        if check_fn is None:
            continue

        discretionary = bool(row.get("discretionary_flag", False))
        ui_flag = str(row.get("ui_flag") or "").strip()
        rule_summary = str(row.get("rule_summary") or "").strip()
        rule_detail = str(row.get("rule_detail") or "").strip()

        message = ui_flag or rule_summary
        suggestion = rule_detail if rule_detail and rule_detail != message else None

        rules.append(
            {
                "id": str(row["rule_id"]),
                "title": rule_summary,
                "message": message,
                "severity": "info" if discretionary else "warn",
                "category": _derive_category(str(row.get("source_file") or "")),
                "suggestion": suggestion,
                "check": check_fn,
            }
        )

    return rules
