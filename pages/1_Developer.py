"""Octavius — Developer Window for iterative rule authoring and testing."""

from __future__ import annotations

import re

import streamlit as st

from logic.engine import get_spacy_status, lint_text
from logic.sandbox import build_regex_check, execute_rule_code
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius — Developer", layout="wide")


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Developer Window")
    st.divider()
    spacy_ok = get_spacy_status()
    st.metric("spaCy model", "loaded" if spacy_ok else "missing")
    if not spacy_ok:
        st.error("spaCy model missing — run:\npython -m spacy download en_core_web_sm")
    st.divider()
    st.markdown(
        "Use this window to write and test a rule before adding it to `logic/rules.py`."
    )

# ── Session state defaults ───────────────────────────────────────────
_DEFAULTS: dict = {
    "dev_text": "The report was written by the team. Mistakes were made.",
    "dev_findings": [],
    "dev_error": None,
    "dev_rule": None,  # compiled rule dict (Python callable survives reruns)
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Starter templates ────────────────────────────────────────────────
_SPACY_TEMPLATE = '''\
def check_my_rule(doc):
    """Detect my pattern using spaCy dependency/POS analysis.

    Must return a list of dicts, each with:
      - start_char (int)  — start of the matched span
      - end_char   (int)  — end of the matched span
      - suggestion (str)  — optional rewrite hint (or omit the key)
    """
    results = []
    for token in doc:
        # Example: flag every passive auxiliary (dep_ == "auxpass")
        if token.dep_ == "auxpass":
            results.append({
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "suggestion": f\'Consider rewriting "{token.head.text}" in active voice.\',
            })
    return results
'''

# ── Layout ───────────────────────────────────────────────────────────
st.header("Rule Developer")

left_col, right_col = st.columns(2, gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Rule editor
# ════════════════════════════════════════════════════════════════════
with left_col:
    st.subheader("Rule Editor")

    mode = st.radio(
        "Input mode",
        ["spaCy Function", "Regex"],
        horizontal=True,
        help=(
            "**spaCy Function** — write a full Python check function using the spaCy Doc API. "
            "**Regex** — enter a pattern; matches are flagged automatically."
        ),
    )

    # ── Rule metadata ────────────────────────────────────────────────
    with st.expander("Rule Metadata", expanded=True):
        meta_id = st.text_input(
            "Rule ID",
            value="DEV-RULE-001",
            help="Unique identifier, e.g. MY-RULE-001",
        )
        meta_title = st.text_input("Title", value="My Custom Rule")
        meta_message = st.text_area(
            "Message shown to user",
            value="This pattern was detected.",
            height=80,
        )
        meta_severity = st.selectbox(
            "Severity",
            ["warn", "error", "info"],
            index=0,
        )

    rule_meta = {
        "id": meta_id,
        "title": meta_title,
        "message": meta_message,
        "severity": meta_severity,
    }

    # ── Code / pattern input ─────────────────────────────────────────
    if mode == "spaCy Function":
        code = st.text_area(
            "check_* function",
            value=_SPACY_TEMPLATE,
            height=340,
            help=(
                "Define **one** function whose name starts with `check_`. "
                "It receives a `spacy.tokens.Doc` and returns a list of dicts."
            ),
        )

        if st.button("Test Rule", type="primary", use_container_width=True):
            rule, error = execute_rule_code(code, rule_meta)
            if error:
                st.session_state["dev_error"] = error
                st.session_state["dev_findings"] = []
                st.session_state["dev_rule"] = None
            else:
                st.session_state["dev_error"] = None
                st.session_state["dev_rule"] = rule
                st.session_state["dev_findings"] = lint_text(
                    st.session_state["dev_text"], [rule]
                )
            st.rerun()

    else:  # Regex mode
        pattern = st.text_input(
            "Regex pattern",
            value=r"\b\w+ed\b",
            help="Python `re` syntax. Each match is flagged as a finding.",
        )

        if st.button("Test Rule", type="primary", use_container_width=True):
            try:
                check_fn = build_regex_check(pattern)
                rule = {
                    "id": rule_meta["id"],
                    "title": rule_meta["title"],
                    "message": rule_meta["message"],
                    "severity": rule_meta["severity"],
                    "suggestion": None,
                    "check": check_fn,
                }
                st.session_state["dev_error"] = None
                st.session_state["dev_rule"] = rule
                st.session_state["dev_findings"] = lint_text(
                    st.session_state["dev_text"], [rule]
                )
            except re.error as exc:
                st.session_state["dev_error"] = f"Invalid regex: {exc}"
                st.session_state["dev_findings"] = []
                st.session_state["dev_rule"] = None
            st.rerun()

    # ── Usage tips ───────────────────────────────────────────────────
    with st.expander("Tips & spaCy quick reference"):
        st.markdown(
            """
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

**Regex mode** auto-wraps your pattern in:
```python
for m in re.finditer(pattern, doc.text):
    yield start_char=m.start(), end_char=m.end()
```
"""
        )

# ════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Test area
# ════════════════════════════════════════════════════════════════════
with right_col:
    st.subheader("Test Area")

    # Error banner
    if st.session_state["dev_error"]:
        st.error(st.session_state["dev_error"])

    # Rule metadata for the React component (metadata only — no callable)
    dev_rule = st.session_state["dev_rule"]
    rules_meta_for_editor = (
        [
            {
                "id":       dev_rule["id"],
                "title":    dev_rule["title"],
                "severity": dev_rule["severity"],
            }
        ]
        if dev_rule is not None
        else []
    )

    # Render the visual editor
    result = st_octavius_editor(
        text=st.session_state["dev_text"],
        findings=[dict(f) for f in st.session_state["dev_findings"]],
        rules=rules_meta_for_editor,
        key="dev_editor",
    )

    # Handle Analyse button clicks from the React component.
    # Re-lint using the stored callable — no need to re-exec user code.
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
                "No rule compiled yet. Click 'Test Rule' first."
            )

        st.rerun()

    # Finding count summary
    n = len(st.session_state["dev_findings"])
    if st.session_state["dev_rule"] is None and not st.session_state["dev_error"]:
        st.info("Define a rule and click **Test Rule** to see findings highlighted above.")
    elif n:
        st.success(f"{n} finding{'s' if n != 1 else ''} detected.")
    else:
        st.info("No findings — rule ran without matches.")
