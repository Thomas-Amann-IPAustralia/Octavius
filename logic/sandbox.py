"""Octavius sandbox — safe execution of user-provided rule code."""

from __future__ import annotations

import collections
import re
import traceback
from typing import Any, Callable, List

import spacy
from spacy.tokens import Doc

# Modules that user code may import.
_ALLOWED_MODULES: dict[str, Any] = {
    "re": re,
    "collections": collections,
    "math": __import__("math"),
    "string": __import__("string"),
}


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """Restricted import that only allows whitelisted modules."""
    mod = _ALLOWED_MODULES.get(name)
    if mod is not None:
        return mod
    raise ImportError(
        f"Module '{name}' is not available. "
        f"Allowed imports: {', '.join(sorted(_ALLOWED_MODULES))}."
    )


# Builtins exposed to user code — deliberately minimal.
_SAFE_BUILTINS: dict[str, Any] = {
    "__import__": _safe_import,
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
    "reversed": reversed,
    "sorted": sorted,
    "map": map,
    "filter": filter,
    "abs": abs,
    "sum": sum,
    "round": round,
    "hasattr": hasattr,
    "getattr": getattr,
    "type": type,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "StopIteration": StopIteration,
}

_SANDBOX_GLOBALS: dict[str, Any] = {
    "re": re,
    "spacy": spacy,
    "Doc": Doc,
    "Any": Any,
    "List": List,
    "collections": collections,
    "defaultdict": collections.defaultdict,
    "__builtins__": _SAFE_BUILTINS,
}


def translate_error(raw: str) -> str:
    """Convert a raw sandbox error string into a plain-language message."""
    if raw.startswith("Syntax error on line"):
        return raw.replace("Syntax error", "Typo or formatting issue in the code")
    if raw.startswith("Runtime error:"):
        return (
            "The code ran but hit a problem. "
            "Details below — share with your developer:\n" + raw
        )
    if "No function starting with 'check_'" in raw:
        return (
            "The pasted code doesn't contain a rule function. "
            "Make sure you copied the complete code from your AI assistant, "
            "including the line that starts with 'def check_'."
        )
    return raw


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
