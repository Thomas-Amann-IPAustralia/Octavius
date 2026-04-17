"""Octavius — FastAPI backend for the standalone frontend."""

from __future__ import annotations

from collections import Counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from logic.engine import lint_text
from logic.rules import RULES

app = FastAPI(title="Octavius", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SEVERITY_MAP = {"warn": "warning"}

_category_index: dict[str, list[dict]] = {}
for _rule in RULES:
    _cat = (_rule.get("category") or "General").lower()
    _category_index.setdefault(_cat, []).append(_rule)


class CheckRequest(BaseModel):
    text: str
    rule_groups: list[str] | None = None


@app.get("/groups")
def get_groups() -> list[dict]:
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for rule in RULES:
        cat = (rule.get("category") or "General")
        key = cat.lower()
        counts[key] += 1
        names[key] = cat
    return [
        {"id": key, "name": names[key], "rule_count": counts[key]}
        for key in sorted(counts)
    ]


@app.post("/check")
def check_text(req: CheckRequest) -> list[dict]:
    if req.rule_groups is not None:
        active_keys = {g.lower() for g in req.rule_groups}
        active_rules = [
            r for cat, rules in _category_index.items()
            if cat in active_keys
            for r in rules
        ]
    else:
        active_rules = list(RULES)

    findings = lint_text(req.text, active_rules)

    rule_cat = {r["id"]: (r.get("category") or "General").lower() for r in RULES}

    return [
        {
            "rule_id": f["rule_id"],
            "group": rule_cat.get(f["rule_id"], "general"),
            "message": f["message"],
            "start": f["start_char"],
            "end": f["end_char"],
            "severity": SEVERITY_MAP.get(f["severity"], f["severity"]),
            "suggestion": f.get("suggestion"),
        }
        for f in findings
    ]
