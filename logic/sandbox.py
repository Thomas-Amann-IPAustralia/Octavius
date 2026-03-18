"""Octavius sandbox — safe execution of user-provided rule code."""

from __future__ import annotations

import re
import traceback
from typing import Any, Callable

import spacy
from spacy.tokens import Doc

# Builtins exposed to user code — deliberately minimal.
_SAFE_BUILTINS: dict[str, Any] = {
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "min": min,
    "max": max,
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "zip": zip,
    "print": print,
}

_SANDBOX_GLOBALS: dict[str, Any] = {
    "re": re,
    "spacy": spacy,
    "Doc": Doc,
    "__builtins__": _SAFE_BUILTINS,
}


def build_regex_check(pattern: str) -> Callable[[Doc], list[dict[str, Any]]]:
    """Return a check function that finds all regex matches in doc.text.

    Raises ``re.error`` if *pattern* is invalid.
    """
    compiled = re.compile(pattern)

    def check_regex(doc: Doc) -> list[dict[str, Any]]:
        return [
            {"start_char": m.start(), "end_char": m.end()}
            for m in compiled.finditer(doc.text)
        ]

    return check_regex


def execute_rule_code(
    code: str,
    rule_meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Compile and execute *code* in a restricted namespace.

    Searches the resulting namespace for the first callable whose name starts
    with ``check_`` and assembles it into a rule dict using *rule_meta*.

    Returns:
        ``(rule_dict, None)`` on success.
        ``(None, error_message)`` on any failure.
    """
    namespace: dict[str, Any] = dict(_SANDBOX_GLOBALS)

    # Compile first so syntax errors surface cleanly.
    try:
        compiled = compile(code, "<developer_rule>", "exec")
    except SyntaxError as exc:
        return None, f"Syntax error on line {exc.lineno}: {exc.msg}"

    # Execute the compiled code.
    try:
        exec(compiled, namespace)  # noqa: S102
    except Exception:
        return None, f"Runtime error:\n{traceback.format_exc()}"

    # Find the check_* function.
    check_fn: Callable | None = None
    for name, obj in namespace.items():
        if name.startswith("check_") and callable(obj):
            check_fn = obj
            break

    if check_fn is None:
        return (
            None,
            "No function starting with 'check_' was found. "
            "Define a function named check_something(doc) that returns a list of dicts.",
        )

    rule: dict[str, Any] = {
        "id":         rule_meta.get("id", "DEV-RULE-001"),
        "title":      rule_meta.get("title", "Developer Rule"),
        "message":    rule_meta.get("message", "Developer rule triggered."),
        "severity":   rule_meta.get("severity", "warn"),
        "suggestion": rule_meta.get("suggestion"),
        "check":      check_fn,
    }

    return rule, None
