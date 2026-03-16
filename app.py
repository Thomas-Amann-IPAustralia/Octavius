"""Octavius — plain-language linter (vertical slice)."""

import streamlit as st
from annotated_text import annotated_text

from logic.engine import get_spacy_status, lint_text
from logic.rules import RULES

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius", layout="wide")

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Plain-language linter — vertical slice")
    st.divider()
    spacy_ok = get_spacy_status()
    st.metric("spaCy model", "loaded" if spacy_ok else "missing")
    st.metric("Active rules", len(RULES))

# ── Session state defaults ───────────────────────────────────────────
if "text" not in st.session_state:
    st.session_state["text"] = ""
if "findings" not in st.session_state:
    st.session_state["findings"] = []

# ── Main area ────────────────────────────────────────────────────────
st.header("Audit")

text = st.text_area(
    "Paste your text below",
    height=200,
    key="text_input",
    value=st.session_state["text"],
)

if st.button("Run audit", type="primary"):
    st.session_state["text"] = text
    st.session_state["findings"] = lint_text(text, RULES)

findings = st.session_state["findings"]

# ── Results ──────────────────────────────────────────────────────────
if findings:
    st.subheader(f"Findings ({len(findings)})")

    # Build annotated-text tokens
    parts: list = []
    prev = 0
    for f in findings:
        if f["start_char"] > prev:
            parts.append(text[prev : f["start_char"]])
        parts.append(
            (text[f["start_char"] : f["end_char"]], f["severity"].upper(), "#ffa500")
        )
        prev = f["end_char"]
    if prev < len(text):
        parts.append(text[prev:])

    annotated_text(*parts)

    st.divider()

    for i, f in enumerate(findings, 1):
        severity_color = {"error": "red", "warn": "orange", "info": "blue"}.get(
            f["severity"], "grey"
        )
        st.markdown(
            f"**:{severity_color}[{f['severity'].upper()}]** "
            f"`{f['rule_id']}` — {f['message']}"
        )
        if f.get("suggestion"):
            st.caption(f.get("suggestion"))

elif st.session_state["text"]:
    st.success("No findings — looking good!")
