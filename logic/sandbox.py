"""Octavius sandbox — safe execution of user-provided rule code."""

from __future__ import annotations

import re
import traceback
from collections import defaultdict
from typing import Any, Callable, Optional

import spacy
from spacy.tokens import Doc

# ── Builtins exposed to user code — deliberately minimal. ────────────
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
    "reversed": reversed,
    "sorted": sorted,
    "abs": abs,
    "sum": sum,
    "map": map,
    "filter": filter,
    "chr": chr,
    "ord": ord,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "type": type,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "StopIteration": StopIteration,
    "Exception": Exception,
}

_SANDBOX_GLOBALS: dict[str, Any] = {
    "re": re,
    "spacy": spacy,
    "Doc": Doc,
    "Any": Any,
    "Callable": Callable,
    "Optional": Optional,
    "defaultdict": defaultdict,
    "__builtins__": _SAFE_BUILTINS,
}


# ── Import-line patterns that can be safely stripped ──────────────────
_IMPORT_LINE_RE = re.compile(
    r"^[ \t]*(?:"
    r"from\s+__future__\s+import\s+annotations"
    r"|import\s+re(?:[ \t]+#.*)?"
    r"|from\s+collections\s+import\s+defaultdict(?:[ \t]+#.*)?"
    r"|from\s+typing\s+import\s+[\w \t,]+(?:[ \t]+#.*)?"
    r"|import\s+spacy(?:[ \t]+#.*)?"
    r"|from\s+spacy(?:\.tokens)?\s+import\s+[\w \t,]+(?:[ \t]+#.*)?"
    r")[ \t]*$",
    re.MULTILINE,
)


def preprocess_code(code: str) -> tuple[str, list[str]]:
    """Strip import statements and boilerplate from pasted rule code.

    Returns ``(cleaned_code, info_messages)`` where *info_messages* lists
    each line that was removed with a human-readable explanation.
    """
    messages: list[str] = []

    def _on_match(m: re.Match) -> str:
        line = m.group().strip()
        messages.append(f"Removed `{line}` (already available in the sandbox)")
        return ""

    cleaned = _IMPORT_LINE_RE.sub(_on_match, code)
    # Collapse leading blank lines left behind.
    cleaned = cleaned.lstrip("\n")
    return cleaned, messages


# ── Part 2 — RULES entry parser ──────────────────────────────────────
_FIELD_RE = {
    "id": re.compile(r'"id"\s*:\s*"([^"]+)"'),
    "title": re.compile(r'"title"\s*:\s*"([^"]+)"'),
    "severity": re.compile(r'"severity"\s*:\s*"([^"]+)"'),
    "category": re.compile(r'"category"\s*:\s*"([^"]+)"'),
}

# message can be a simple string or a parenthesised multi-line string
_MESSAGE_SIMPLE_RE = re.compile(r'"message"\s*:\s*"([^"]+)"')
_MESSAGE_PAREN_RE = re.compile(
    r'"message"\s*:\s*\(\s*((?:"[^"]*"\s*)+)\)', re.DOTALL
)


def parse_rules_entry(text: str) -> dict[str, str] | None:
    """Extract rule metadata from a pasted Part 2 RULES dict.

    Returns a dict with keys ``id``, ``title``, ``message``, ``severity``
    (and optionally ``category``), or *None* if parsing fails.
    """
    result: dict[str, str] = {}
    for key, pattern in _FIELD_RE.items():
        m = pattern.search(text)
        if m:
            result[key] = m.group(1)

    # Try simple message first, fall back to parenthesised form.
    m = _MESSAGE_SIMPLE_RE.search(text)
    if m:
        result["message"] = m.group(1)
    else:
        m = _MESSAGE_PAREN_RE.search(text)
        if m:
            # Join the individual quoted strings.
            raw = m.group(1)
            parts = re.findall(r'"([^"]*)"', raw)
            result["message"] = "".join(parts)

    if "id" in result:
        return result
    return None


# ── Part 3 — Test examples parser ────────────────────────────────────
_TEST_VAR_RE = re.compile(
    r'(_\w+?_(FIRE|SKIP))\s*=\s*'
    r'(?:'
    r'"""\\?\n?(.*?)"""'     # triple-double-quoted
    r"|'''\\?\n?(.*?)'''"    # triple-single-quoted
    r")",
    re.DOTALL,
)


def parse_test_examples(text: str) -> list[tuple[str, str, str]]:
    """Parse Part 3 test text into structured test cases.

    Returns a list of ``(label, text_content, "fire"|"skip")`` tuples.

    Recognises patterns like::

        _CLAUSES_001_FIRE = \"\"\"\\ ...\"\"\"
        _CLAUSES_001_SKIP = \"\"\"\\ ...\"\"\"

    If no such pattern is detected, returns the raw text as a single
    ``("Test text", raw_text, "fire")`` entry.
    """
    matches = _TEST_VAR_RE.findall(text)
    if not matches:
        stripped = text.strip()
        if stripped:
            return [("Test text", stripped, "fire")]
        return []

    results: list[tuple[str, str, str]] = []
    for var_name, kind, content_dq, content_sq in matches:
        content = (content_dq or content_sq).strip()
        label = var_name.lstrip("_")
        expect = kind.lower()  # "fire" or "skip"
        results.append((label, content, expect))
    return results


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
