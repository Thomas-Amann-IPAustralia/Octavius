"""Octavius — Developer window for rule testing and authoring."""

from __future__ import annotations

import re as _re

import streamlit as st

from logic.engine import get_spacy_status, lint_text
try:
    from logic.sandbox import (
        build_regex_check,
        execute_rule_code,
        parse_rules_entry,
        parse_test_examples,
        preprocess_code,
        translate_error,
    )
except ImportError as _sandbox_err:
    st.error(
        f"**Developer tools failed to load.**\n\n"
        f"`logic/sandbox.py` could not be imported: `{_sandbox_err}`\n\n"
        "Ensure `logic/sandbox.py` is present and all dependencies are installed."
    )
    st.stop()
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius — Developer", layout="wide")


# ── Helpers ──────────────────────────────────────────────────────────
def _make_rule_id(title: str) -> str:
    """Convert a human title to a slug-style rule ID, e.g. MY-RULE-001."""
    slug = _re.sub(r"[^a-zA-Z0-9]+", "-", title).upper().strip("-")
    return f"{slug}-001" if slug else "MY-RULE-001"


_SEVERITY_LABELS = {"Warning": "warn", "Error": "error", "Info": "info"}
_SEVERITY_LABEL_DEFAULT = "Warning"
_SEVERITY_REVERSE = {v: k for k, v in _SEVERITY_LABELS.items()}


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Developer Window")
    st.divider()
    st.markdown(
        """
**Rule Tester** — paste code from the rules spreadsheet and test it immediately.

**Rule Builder** — create a new rule from scratch with AI assistance.
"""
    )
    with st.expander("System status"):
        spacy_ok = get_spacy_status()
        st.metric("spaCy model", "loaded" if spacy_ok else "missing")
        if not spacy_ok:
            st.error(
                "spaCy model missing — run:\npython -m spacy download en_core_web_sm"
            )


# ── Session state defaults ───────────────────────────────────────────
_DEFAULTS: dict = {
    # Rule Tester state
    "tester_code": "",
    "tester_rules_entry": "",
    "tester_test_input": "",
    "tester_rule": None,
    "tester_results": [],  # list of (label, expect, findings, test_text)
    "tester_error": None,
    "tester_cleanup_log": [],
    "tester_active_case": 0,
    # Rule Builder state (existing)
    "dev_text": "The report was written by the team. Mistakes were made.",
    "dev_findings": [],
    "dev_error": None,
    "dev_rule": None,
    "dev_code": "",
    "dev_title": "My custom rule",
    "dev_message": "This pattern was detected.",
    "dev_severity_label": _SEVERITY_LABEL_DEFAULT,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Layout ───────────────────────────────────────────────────────────
st.header("Developer Window")

tab_tester, tab_builder = st.tabs(["Rule Tester", "Rule Builder"])


# ╔════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — RULE TESTER (for spreadsheet users)                     ║
# ╚════════════════════════════════════════════════════════════════════╝
with tab_tester:

    tester_left, tester_right = st.columns([1, 1], gap="large")

    # ── LEFT COLUMN — Inputs ─────────────────────────────────────────
    with tester_left:

        # ── Paste check function ─────────────────────────────────────
        st.subheader("1. Paste check function")
        st.markdown(
            "Paste the code from **Part 1 — Check function** in the spreadsheet. "
            "Import statements like `import re` are handled automatically."
        )
        with st.expander("What does the code need?", expanded=False):
            st.markdown(
                """
The code must contain a Python function starting with `def check_`. For example:

```python
def check_my_rule(doc: Doc) -> list[dict]:
    results = []
    for token in doc:
        if token.dep_ == "auxpass":
            # ... detect and append findings
            results.append({
                "start_char": ...,
                "end_char": ...,
                "suggestion": "..."
            })
    return results
```

**What's handled automatically:**
- `import re`, `from collections import defaultdict`, `from typing import ...` — removed (already available)
- Module-level constants like `_MY_RE = re.compile(...)` — work fine
- Comments and docstrings — preserved

**What each finding dict must contain:**
- `start_char` (int) — where the issue starts in the text
- `end_char` (int) — where the issue ends
- `suggestion` (str, optional) — fix suggestion shown to the user
"""
            )

        tester_code = st.text_area(
            "Check function code",
            value=st.session_state["tester_code"],
            key="tester_code",
            height=250,
            placeholder=(
                "def check_my_rule(doc: Doc) -> list[dict]:\n"
                "    results = []\n"
                "    # ... paste code from Part 1 ...\n"
                "    return results"
            ),
            label_visibility="collapsed",
        )

        st.divider()

        # ── Paste rule details (optional) ────────────────────────────
        st.subheader("2. Paste rule details (optional)")
        st.markdown(
            "Paste the dict from **Part 2 — RULES entry** to auto-fill "
            "rule metadata. Or skip this — defaults will be used."
        )

        tester_rules_entry = st.text_area(
            "RULES entry",
            value=st.session_state["tester_rules_entry"],
            key="tester_rules_entry",
            height=120,
            placeholder='{\n    "id": "MY-RULE-001",\n    "title": "...",\n    ...\n}',
            label_visibility="collapsed",
        )

        # Parse and display what was extracted
        parsed_meta = None
        if tester_rules_entry.strip():
            parsed_meta = parse_rules_entry(tester_rules_entry)
            if parsed_meta:
                cols = st.columns(2)
                with cols[0]:
                    st.caption(f"**ID:** `{parsed_meta.get('id', '—')}`")
                    st.caption(f"**Title:** {parsed_meta.get('title', '—')}")
                with cols[1]:
                    st.caption(f"**Severity:** `{parsed_meta.get('severity', '—')}`")
                    st.caption(f"**Category:** {parsed_meta.get('category', '—')}")
            else:
                st.warning(
                    "Could not parse rule details. Check that the pasted text "
                    "contains `\"id\": \"...\"` at minimum."
                )

        st.divider()

        # ── Paste test examples ──────────────────────────────────────
        st.subheader("3. Paste test examples")
        st.markdown(
            "Paste from **Part 3 — Test examples** in the spreadsheet, "
            "or type your own test sentences."
        )
        with st.expander("Supported formats", expanded=False):
            st.markdown(
                """
**Spreadsheet format** (auto-detected):
```python
_MY_RULE_FIRE = \"\"\"
Text that should trigger the rule.
\"\"\"

_MY_RULE_SKIP = \"\"\"
Clean text that should not trigger.
\"\"\"
```
- `_FIRE` variables = text that **should** trigger findings (shown in green if it does)
- `_SKIP` variables = text that **should not** trigger findings (shown in green if clean)

**Plain text** — just type or paste sentences directly. Each will be tested as-is.
"""
            )

        tester_test_input = st.text_area(
            "Test examples",
            value=st.session_state["tester_test_input"],
            key="tester_test_input",
            height=150,
            placeholder=(
                "Type test sentences here, or paste Part 3 from the spreadsheet.\n\n"
                "Example: The report was written by the team."
            ),
            label_visibility="collapsed",
        )

        st.divider()

        # ── Test button ──────────────────────────────────────────────
        if st.button(
            "Test Rule",
            type="primary",
            use_container_width=True,
            key="tester_run_btn",
        ):
            if not tester_code.strip():
                st.session_state["tester_error"] = (
                    "The code box is empty. Paste the check function from "
                    "Part 1 of the spreadsheet."
                )
                st.session_state["tester_results"] = []
                st.session_state["tester_rule"] = None
                st.session_state["tester_cleanup_log"] = []
            elif not tester_test_input.strip():
                st.session_state["tester_error"] = (
                    "No test text provided. Paste examples from Part 3 of "
                    "the spreadsheet, or type your own test sentences."
                )
                st.session_state["tester_results"] = []
                st.session_state["tester_rule"] = None
                st.session_state["tester_cleanup_log"] = []
            else:
                # 1. Preprocess code
                cleaned_code, cleanup_msgs = preprocess_code(tester_code)
                st.session_state["tester_cleanup_log"] = cleanup_msgs

                # 2. Build rule metadata
                if parsed_meta:
                    rule_meta = {
                        "id": parsed_meta.get("id", "DEV-RULE-001"),
                        "title": parsed_meta.get("title", "Developer Rule"),
                        "message": parsed_meta.get("message", "Rule triggered."),
                        "severity": parsed_meta.get("severity", "warn"),
                    }
                else:
                    rule_meta = {
                        "id": "DEV-RULE-001",
                        "title": "Developer Rule",
                        "message": "Rule triggered.",
                        "severity": "warn",
                    }

                # 3. Execute code in sandbox
                rule, error = execute_rule_code(cleaned_code, rule_meta)
                if error:
                    st.session_state["tester_error"] = translate_error(error)
                    st.session_state["tester_results"] = []
                    st.session_state["tester_rule"] = None
                else:
                    st.session_state["tester_error"] = None
                    st.session_state["tester_rule"] = rule

                    # 4. Parse test examples and run against each
                    test_cases = parse_test_examples(tester_test_input)
                    results = []
                    for label, test_text, expect in test_cases:
                        try:
                            findings = lint_text(test_text, [rule])
                        except Exception as exc:
                            st.session_state["tester_error"] = (
                                f"Rule compiled but crashed when processing test text. "
                                f"Error: {exc}"
                            )
                            st.session_state["tester_results"] = []
                            st.session_state["tester_rule"] = None
                            break
                        results.append((label, expect, findings, test_text))
                    else:
                        st.session_state["tester_results"] = results
                        st.session_state["tester_active_case"] = 0

            st.rerun()

        # ── Feedback messages ────────────────────────────────────────
        if st.session_state["tester_error"]:
            st.error(st.session_state["tester_error"])

    # ── RIGHT COLUMN — Results ───────────────────────────────────────
    with tester_right:
        st.subheader("Results")

        # Cleanup log
        cleanup_log = st.session_state.get("tester_cleanup_log", [])
        if cleanup_log:
            with st.expander("Code cleanup log", expanded=True):
                for msg in cleanup_log:
                    st.info(msg, icon="🔧")

        # Test results
        results = st.session_state.get("tester_results", [])
        tester_rule = st.session_state.get("tester_rule")

        if results:
            # Summary
            total = len(results)
            passed = 0
            for label, expect, findings, test_text in results:
                if expect == "fire" and len(findings) > 0:
                    passed += 1
                elif expect == "skip" and len(findings) == 0:
                    passed += 1
            # Only show pass/fail summary when there are classified cases
            has_classified = any(e in ("fire", "skip") for _, e, _, _ in results)
            if has_classified:
                if passed == total:
                    st.success(f"All {total} test cases passed.")
                else:
                    st.warning(f"{passed} of {total} test cases passed.")

            # Per-case results
            for i, (label, expect, findings, test_text) in enumerate(results):
                n = len(findings)

                if expect == "fire":
                    status = "PASS" if n > 0 else "FAIL"
                    expect_desc = "should trigger"
                elif expect == "skip":
                    status = "PASS" if n == 0 else "FAIL"
                    expect_desc = "should NOT trigger"
                else:
                    status = ""
                    expect_desc = ""

                # Build header
                if status == "PASS":
                    icon = "✅"
                elif status == "FAIL":
                    icon = "❌"
                else:
                    icon = "🔍"

                header = f"{icon} **{label}**"
                if expect_desc:
                    header += f" ({expect_desc})"
                header += f" — {n} finding{'s' if n != 1 else ''}"

                with st.expander(header, expanded=(status == "FAIL" or i == 0)):
                    # Show the highlighted text preview
                    if tester_rule is not None:
                        rules_meta = [
                            {
                                "id": tester_rule["id"],
                                "title": tester_rule["title"],
                                "severity": tester_rule["severity"],
                            }
                        ]
                    else:
                        rules_meta = []

                    st_octavius_editor(
                        text=test_text,
                        findings=[dict(f) for f in findings],
                        rules=rules_meta,
                        key=f"tester_preview_{i}",
                    )

                    # Finding details
                    if findings:
                        st.markdown("**Findings:**")
                        for j, f in enumerate(findings):
                            span_text = test_text[f["start_char"]:f["end_char"]]
                            suggestion = f.get("suggestion") or "—"
                            st.markdown(
                                f"{j+1}. **\"{span_text}\"** "
                                f"(chars {f['start_char']}–{f['end_char']})"
                                f"  \nSuggestion: {suggestion}"
                            )

        elif tester_rule is not None and not st.session_state["tester_error"]:
            st.info("Rule compiled successfully but no test results to display.")
        elif not st.session_state["tester_error"]:
            st.info(
                "Paste the check function (Part 1), test examples (Part 3), "
                "and click **Test Rule** to see results here."
            )


# ╔════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — RULE BUILDER (existing step-by-step workflow)           ║
# ╚════════════════════════════════════════════════════════════════════╝
with tab_builder:

    left_col, right_col = st.columns(2, gap="large")

    # ── LEFT COLUMN — Step-by-step workflow ──────────────────────────
    with left_col:

        # ── Step 1 — Describe your rule ──────────────────────────────
        st.subheader("Step 1 — Describe your rule")

        meta_title = st.text_input(
            "Rule name",
            value=st.session_state["dev_title"],
            key="dev_title",
            help="A short name for the rule, e.g. 'Passive voice' or 'Jargon words'.",
        )
        meta_message = st.text_area(
            "What should it tell the user?",
            value=st.session_state["dev_message"],
            key="dev_message",
            height=80,
            help="The message shown when the rule fires, e.g. 'Avoid passive voice — rewrite in active voice.'",
        )
        severity_label = st.selectbox(
            "How serious is this issue?",
            list(_SEVERITY_LABELS.keys()),
            index=list(_SEVERITY_LABELS.keys()).index(
                st.session_state["dev_severity_label"]
            ),
            key="dev_severity_label",
            help="**Warning** — common style issue. **Error** — must fix. **Info** — helpful note.",
        )
        meta_severity = _SEVERITY_LABELS[severity_label]
        rule_id = _make_rule_id(meta_title)
        st.caption(f"Rule ID (auto-generated): `{rule_id}`")

        rule_meta = {
            "id": rule_id,
            "title": meta_title,
            "message": meta_message,
            "severity": meta_severity,
        }

        st.divider()

        # ── Step 2 — Get the code from an AI assistant ───────────────
        st.subheader("Step 2 — Get the code from an AI assistant")
        st.markdown(
            "Copy the prompt below and paste it into **Claude** or **ChatGPT**. "
            "It's already filled in with what you entered above."
        )

        ai_prompt = f"""\
Write a Python function for a plain-language linter rule called "{meta_title}".

The function must:
- Be named check_something (any name starting with check_)
- Accept a single argument: doc (a spaCy Doc object)
- Return a list of dicts, each with: start_char (int), end_char (int), and optionally suggestion (str)

Rule purpose: {meta_message}

Use spaCy token attributes such as token.dep_, token.pos_, token.lemma_, token.text, and token.idx.
To highlight a span of tokens: use span.start_char and span.end_char.
Do not import anything — spaCy's Doc, re, and standard Python builtins are already available.

Return only the Python function, no explanation needed.\
"""

        st.code(ai_prompt, language=None)

        st.divider()

        # ── Step 3 — Paste the generated code ────────────────────────
        st.subheader("Step 3 — Paste the generated code")
        st.markdown("Paste the code you received from your AI assistant into the box below.")

        code = st.text_area(
            "Generated rule code",
            value=st.session_state["dev_code"],
            key="dev_code",
            height=260,
            placeholder="def check_my_rule(doc):\n    results = []\n    # ... paste here ...\n    return results",
            label_visibility="collapsed",
        )

        st.divider()

        # ── Step 4 — Test the rule ───────────────────────────────────
        st.subheader("Step 4 — Test the rule")
        st.markdown(
            "Enter some example sentences below. "
            "Anything the rule should flag will be highlighted in the preview on the right."
        )

        st.text_area(
            "Test text",
            key="dev_text",
            height=100,
            label_visibility="collapsed",
        )

        if st.button("▶  Test Rule", type="primary", use_container_width=True):
            if not code.strip():
                st.session_state["dev_error"] = (
                    "The code box is empty. "
                    "Complete Step 2 to get code from an AI assistant, then paste it in Step 3."
                )
                st.session_state["dev_findings"] = []
                st.session_state["dev_rule"] = None
            else:
                # Preprocess code before execution (same as Rule Tester)
                cleaned_code, _cleanup = preprocess_code(code)
                rule, error = execute_rule_code(cleaned_code, rule_meta)
                if error:
                    st.session_state["dev_error"] = translate_error(error)
                    st.session_state["dev_findings"] = []
                    st.session_state["dev_rule"] = None
                else:
                    st.session_state["dev_error"] = None
                    st.session_state["dev_rule"] = rule
                    st.session_state["dev_findings"] = lint_text(
                        st.session_state["dev_text"], [rule]
                    )
            st.rerun()

        # Feedback
        if st.session_state["dev_error"]:
            st.error(st.session_state["dev_error"])
        elif st.session_state["dev_rule"] is not None:
            n = len(st.session_state["dev_findings"])
            if n:
                st.success(
                    f"Rule compiled and found {n} match{'es' if n != 1 else ''} in your test text."
                )
            else:
                st.info(
                    "Rule compiled. No matches in the test text — "
                    "try different sentences, or check that the rule logic is correct."
                )

        st.divider()

        # ── Step 5 — Copy for export ─────────────────────────────────
        st.subheader("Step 5 — Copy for export")

        dev_rule = st.session_state["dev_rule"]
        if dev_rule is None:
            st.info("Complete Steps 1–4 first. Once your rule works, the export block will appear here.")
        else:
            st.success(
                "Your rule is working! Copy the two blocks below and send them to your developer."
            )

            # Derive the function name from the compiled callable
            check_fn_name = dev_rule["check"].__name__

            st.markdown("**The rule function** (from Step 3):")
            st.code(code, language="python")

            st.markdown("**The rule registration block** (add this to `logic/rules.py`):")
            export_block = (
                f'{{\n'
                f'    "id": "{dev_rule["id"]}",\n'
                f'    "title": "{dev_rule["title"]}",\n'
                f'    "message": "{dev_rule["message"]}",\n'
                f'    "severity": "{dev_rule["severity"]}",\n'
                f'    "category": "Custom",\n'
                f'    "suggestion": None,\n'
                f'    "check": {check_fn_name},\n'
                f'}}'
            )
            st.code(export_block, language="python")

        st.divider()

        # ── Advanced (collapsed) ─────────────────────────────────────
        with st.expander("Advanced — Regex mode and spaCy reference"):
            st.markdown(
                "**Regex mode** — if your AI assistant gives you a regex pattern instead of a function, "
                "enter it here and click Test."
            )
            pattern = st.text_input(
                "Regex pattern",
                value=r"\b\w+ed\b",
                help="Python `re` syntax. Each match is flagged as a finding.",
            )
            if st.button("Test Regex", use_container_width=True):
                try:
                    check_fn = build_regex_check(pattern)
                    adv_rule = {
                        "id": rule_meta["id"],
                        "title": rule_meta["title"],
                        "message": rule_meta["message"],
                        "severity": rule_meta["severity"],
                        "suggestion": None,
                        "check": check_fn,
                    }
                    st.session_state["dev_error"] = None
                    st.session_state["dev_rule"] = adv_rule
                    st.session_state["dev_findings"] = lint_text(
                        st.session_state["dev_text"], [adv_rule]
                    )
                except _re.error as exc:
                    st.session_state["dev_error"] = f"Invalid regex pattern: {exc}"
                    st.session_state["dev_findings"] = []
                    st.session_state["dev_rule"] = None
                st.rerun()

            st.markdown(
                """
---
**spaCy token attributes** (use on `token` in a `for token in doc` loop):

| Attribute | Example value | Meaning |
|-----------|---------------|---------|
| `token.text` | `"written"` | Surface form |
| `token.lemma_` | `"write"` | Base form |
| `token.pos_` | `"VERB"` | Coarse POS tag |
| `token.tag_` | `"VBN"` | Fine-grained POS |
| `token.dep_` | `"auxpass"` | Dependency relation |
| `token.idx` | `4` | Character start offset |
| `token.head` | `Token` | Syntactic head token |

**Common dependency labels:** `nsubj`, `dobj`, `auxpass`, `aux`, `amod`, `prep`

**Span from tokens:**
```python
span = doc[start_token_i : end_token_i + 1]
start_char = span.start_char
end_char   = span.end_char
```
"""
            )


    # ── RIGHT COLUMN — Visual test area ──────────────────────────────
    with right_col:
        st.subheader("Preview")

        dev_rule = st.session_state["dev_rule"]
        rules_meta_for_editor = (
            [
                {
                    "id": dev_rule["id"],
                    "title": dev_rule["title"],
                    "severity": dev_rule["severity"],
                }
            ]
            if dev_rule is not None
            else []
        )

        result = st_octavius_editor(
            text=st.session_state["dev_text"],
            findings=[dict(f) for f in st.session_state["dev_findings"]],
            rules=rules_meta_for_editor,
            key="dev_editor",
        )

        if result is not None:
            new_text: str = result.get("text", "")
            st.session_state["dev_text"] = new_text

            if st.session_state["dev_rule"] is not None:
                st.session_state["dev_findings"] = lint_text(
                    new_text, [st.session_state["dev_rule"]]
                )
            else:
                st.session_state["dev_findings"] = []
                st.session_state["dev_error"] = (
                    "Test your rule first (Step 4) before using the Analyse button."
                )

            st.rerun()

        if dev_rule is None and not st.session_state["dev_error"]:
            st.info("Complete Step 4 to see findings highlighted here.")
