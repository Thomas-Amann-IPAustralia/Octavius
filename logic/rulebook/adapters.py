"""Adapters: compile one raw rulebook row into a uniform CompiledRule.

Each public function accepts a raw row dict (as read from the parquet) and
returns a CompiledRule whose ``check(text)`` callable produces Findings.

Execution model
---------------
- regex   : trigger_code is a bare regex pattern string.
- lookup  : trigger_code defines ``check_rule(text, lookup_list) -> list[str]``.
- structural: trigger_code defines ``check_rule(text) -> list[str]``.

For lookup and structural, the code is compiled once at startup via Python's
built-in ``compile()`` + ``exec()`` in a controlled namespace, then the
resulting ``check_rule`` function is captured in a closure.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from logic.rulebook.spans import find_term_spans
from logic.rulebook.types import CompiledRule, Finding

# ---------------------------------------------------------------------------
# Execution namespace for trigger code
# ---------------------------------------------------------------------------

# Trigger codes may contain ``import re``, ``from collections import Counter``,
# ``from datetime import date``, etc.  Providing real __builtins__ lets these
# imports resolve while still isolating the namespace from the host process
# globals.  The rules are trusted (test_result == "pass") server-side code.
_RULE_EXEC_GLOBALS: dict[str, Any] = {
    "re": re,
    "defaultdict": defaultdict,
    "__builtins__": __builtins__,
}


def _make_exec_ns() -> dict[str, Any]:
    return dict(_RULE_EXEC_GLOBALS)


# ---------------------------------------------------------------------------
# Severity helper
# ---------------------------------------------------------------------------

def _severity(row: dict) -> str:
    return "info" if row.get("discretionary_flag") else "warning"


# ---------------------------------------------------------------------------
# Public adapter functions
# ---------------------------------------------------------------------------

def compile_regex(row: dict) -> CompiledRule:
    """Compile a regex-taxonomy rule row into a CompiledRule.

    Raises ``re.error`` if the pattern is invalid.
    """
    pattern_str: str = row["trigger_code"]
    compiled_pattern = re.compile(pattern_str, re.IGNORECASE)

    rule_id: str = row["rule_id"]
    taxonomy: str = row["taxonomy"]
    ui_flag: str = row.get("ui_flag") or ""
    rule_summary: str = row.get("rule_summary") or ""
    source_url: str = row.get("source_url") or ""
    severity: str = _severity(row)

    def check(text: str) -> list[Finding]:
        return [
            Finding(
                start_char=m.start(),
                end_char=m.end(),
                rule_id=rule_id,
                taxonomy=taxonomy,
                ui_flag=ui_flag,
                rule_summary=rule_summary,
                source_url=source_url,
                severity=severity,
                document_level=False,
            )
            for m in compiled_pattern.finditer(text)
        ]

    return CompiledRule(
        rule_id=rule_id,
        taxonomy="regex",
        ui_flag=ui_flag,
        rule_summary=rule_summary,
        source_url=source_url,
        severity=severity,
        check=check,
    )


def compile_lookup(row: dict) -> CompiledRule:
    """Compile a lookup-taxonomy rule row into a CompiledRule.

    Raises ``SyntaxError`` or ``RuntimeError`` if the trigger code is invalid.
    """
    trigger_code: str = row["trigger_code"]
    lookup_list: list[str] = list(row.get("lookup_list") or [])

    rule_id: str = row["rule_id"]
    taxonomy: str = row["taxonomy"]
    ui_flag: str = row.get("ui_flag") or ""
    rule_summary: str = row.get("rule_summary") or ""
    source_url: str = row.get("source_url") or ""
    severity: str = _severity(row)

    check_fn = _compile_check_rule(trigger_code, rule_id)

    def check(text: str) -> list[Finding]:
        matched_terms: list[str] = check_fn(text, lookup_list) or []
        findings: list[Finding] = []
        for term in matched_terms:
            spans = find_term_spans(text, str(term))
            if spans:
                for start, end in spans:
                    findings.append(
                        Finding(
                            start_char=start,
                            end_char=end,
                            rule_id=rule_id,
                            taxonomy=taxonomy,
                            ui_flag=ui_flag,
                            rule_summary=rule_summary,
                            source_url=source_url,
                            severity=severity,
                            document_level=False,
                        )
                    )
            else:
                findings.append(
                    Finding(
                        start_char=0,
                        end_char=0,
                        rule_id=rule_id,
                        taxonomy=taxonomy,
                        ui_flag=ui_flag,
                        rule_summary=rule_summary,
                        source_url=source_url,
                        severity=severity,
                        document_level=True,
                    )
                )
        return findings

    return CompiledRule(
        rule_id=rule_id,
        taxonomy="lookup",
        ui_flag=ui_flag,
        rule_summary=rule_summary,
        source_url=source_url,
        severity=severity,
        check=check,
    )


def compile_structural(row: dict) -> CompiledRule:
    """Compile a structural-taxonomy rule row into a CompiledRule.

    Raises ``SyntaxError`` or ``RuntimeError`` if the trigger code is invalid.
    """
    trigger_code: str = row["trigger_code"]

    rule_id: str = row["rule_id"]
    taxonomy: str = row["taxonomy"]
    ui_flag: str = row.get("ui_flag") or ""
    rule_summary: str = row.get("rule_summary") or ""
    source_url: str = row.get("source_url") or ""
    severity: str = _severity(row)

    check_fn = _compile_check_rule(trigger_code, rule_id)

    def check(text: str) -> list[Finding]:
        result = check_fn(text)
        if not result:
            return []

        # Normalise to a list of strings
        if isinstance(result, (list, tuple)):
            items = [str(i) for i in result]
        else:
            items = [str(result)]

        findings: list[Finding] = []
        for item in items:
            spans = find_term_spans(text, item)
            if spans:
                for start, end in spans:
                    findings.append(
                        Finding(
                            start_char=start,
                            end_char=end,
                            rule_id=rule_id,
                            taxonomy=taxonomy,
                            ui_flag=ui_flag,
                            rule_summary=rule_summary,
                            source_url=source_url,
                            severity=severity,
                            document_level=False,
                        )
                    )
            else:
                findings.append(
                    Finding(
                        start_char=0,
                        end_char=0,
                        rule_id=rule_id,
                        taxonomy=taxonomy,
                        ui_flag=ui_flag,
                        rule_summary=rule_summary,
                        source_url=source_url,
                        severity=severity,
                        document_level=True,
                    )
                )
        return findings

    return CompiledRule(
        rule_id=rule_id,
        taxonomy="structural",
        ui_flag=ui_flag,
        rule_summary=rule_summary,
        source_url=source_url,
        severity=severity,
        check=check,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compile_check_rule(trigger_code: str, rule_id: str) -> Callable:
    """Compile *trigger_code* and extract the ``check_rule`` callable.

    Raises ``SyntaxError`` on invalid syntax, or ``ValueError`` if no
    ``check_rule`` function is defined after execution.
    """
    try:
        compiled = compile(trigger_code, f"<rule:{rule_id}>", "exec")
    except SyntaxError as exc:
        raise SyntaxError(
            f"Syntax error in trigger_code for {rule_id}: {exc}"
        ) from exc

    ns = _make_exec_ns()
    exec(compiled, ns)  # noqa: S102

    check_fn: Callable | None = ns.get("check_rule")
    if check_fn is None:
        # Fall back to first callable starting with 'check_'
        for name, obj in ns.items():
            if name.startswith("check_") and callable(obj):
                check_fn = obj
                break

    if check_fn is None or not callable(check_fn):
        raise ValueError(
            f"trigger_code for {rule_id} does not define a callable check_rule()"
        )

    return check_fn
