"""Octavius — Rule Builder for iterative rule authoring and testing."""

from __future__ import annotations

import re as _re

import streamlit as st

from logic.engine import get_spacy_status, lint_text
from logic.sandbox import build_regex_check, execute_rule_code, translate_error
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius — Rule Builder", layout="wide")


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Rule Builder")
    st.divider()
    st.markdown(
        """
**How it works:**

1. Paste the rule code into **Step 1**
2. Click **Test Rule** in **Step 2** to see it in action
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
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# Fixed rule metadata used when executing/testing
_RULE_META = {
    "id": "DEV-RULE-001",
    "title": "Custom rule",
    "message": "This pattern was detected.",
    "severity": "warn",
}


# ── Layout ───────────────────────────────────────────────────────────
st.header("Rule Builder")

left_col, right_col = st.columns(2, gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Step-by-step workflow
# ════════════════════════════════════════════════════════════════════
with left_col:

    # ── Step 1 — Paste the generated code ───────────────────────────
    st.subheader("Step 1 — Paste the generated code")
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

    # ── Step 2 — Test the rule ───────────────────────────────────────
    st.subheader("Step 2 — Test the rule")
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
                "Paste the generated code into Step 1 first."
            )
            st.session_state["dev_findings"] = []
            st.session_state["dev_rule"] = None
        else:
            rule, error = execute_rule_code(code, _RULE_META)
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
                    **_RULE_META,
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
                "Test your rule first (Step 2) before using the Analyse button."
            )

        st.rerun()

    if dev_rule is None and not st.session_state["dev_error"]:
        st.info("Complete Step 2 to see findings highlighted here.")
