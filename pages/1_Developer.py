"""Octavius — Rule Builder for iterative rule authoring and testing."""

from __future__ import annotations

import re as _re

import streamlit as st

from logic.engine import get_spacy_status, lint_text
from logic.sandbox import build_regex_check, execute_rule_code, translate_error
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius — Rule Builder", layout="wide")


# ── Helpers ──────────────────────────────────────────────────────────
def _make_rule_id(title: str) -> str:
    """Convert a human title to a slug-style rule ID, e.g. MY-RULE-001."""
    slug = _re.sub(r"[^a-zA-Z0-9]+", "-", title).upper().strip("-")
    return f"{slug}-001" if slug else "MY-RULE-001"


_SEVERITY_LABELS = {"Warning": "warn", "Error": "error", "Info": "info"}
_SEVERITY_LABEL_DEFAULT = "Warning"


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Rule Builder")
    st.divider()
    st.markdown(
        """
**How it works:**

1. Describe your rule in **Step 1**
2. Copy the AI prompt in **Step 2** and paste it into Claude or ChatGPT
3. Paste the code you get back into **Step 3**
4. Click **Test Rule** in **Step 4** to see it in action
5. Copy the export block in **Step 5** and send it to your developer
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
st.header("Rule Builder")

left_col, right_col = st.columns(2, gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Step-by-step workflow
# ════════════════════════════════════════════════════════════════════
with left_col:

    # ── Step 1 — Describe your rule ──────────────────────────────────
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

    # ── Step 2 — Get the code from an AI assistant ───────────────────
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

    # ── Step 3 — Paste the generated code ───────────────────────────
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

    # ── Step 4 — Test the rule ───────────────────────────────────────
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
            rule, error = execute_rule_code(code, rule_meta)
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
                f"✅ Rule compiled and found {n} match{'es' if n != 1 else ''} in your test text."
            )
        else:
            st.info(
                "✅ Rule compiled. No matches in the test text — "
                "try different sentences, or check that the rule logic is correct."
            )

    st.divider()

    # ── Step 5 — Copy for export ─────────────────────────────────────
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

    # ── Advanced (collapsed) ─────────────────────────────────────────
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


# ════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Visual test area
# ════════════════════════════════════════════════════════════════════
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
