"""Octavius — plain-language linter with React visual editor."""

import streamlit as st

from logic.engine import get_spacy_status, lint_text
from logic.rules import RULES
from octavius_component import st_octavius_editor

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius", layout="wide")


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Octavius")
    st.caption("Plain-language linter")
    st.divider()
    spacy_ok = get_spacy_status()
    st.metric("spaCy model", "loaded" if spacy_ok else "missing")
    st.metric("Rules loaded", len(RULES))
    if not spacy_ok:
        st.error("spaCy model missing — run:\npython -m spacy download en_core_web_sm")

# ── Session state defaults ───────────────────────────────────────────
if "text" not in st.session_state:
    st.session_state["text"] = ""
if "findings" not in st.session_state:
    st.session_state["findings"] = []

# ── Serialise rules for the React component (metadata only) ──────────
rules_meta = [
    {
        "id":       r["id"],
        "title":    r["title"],
        "severity": r["severity"],
        "category": r.get("category", "General"),
    }
    for r in RULES
]

# ── Render the visual editor ─────────────────────────────────────────
result = st_octavius_editor(
    text=st.session_state["text"],
    findings=[dict(f) for f in st.session_state["findings"]],
    rules=rules_meta,
    key="editor",
)

# ── Handle Analyse button clicks from React ───────────────────────────
# React sends { text, activeRuleIds } when the user clicks Analyse.
if result is not None:
    new_text: str       = result.get("text", "")
    active_ids: list    = result.get("activeRuleIds", [r["id"] for r in RULES])

    active_rules = [r for r in RULES if r["id"] in active_ids]

    st.session_state["text"]     = new_text
    st.session_state["findings"] = lint_text(new_text, active_rules)
    st.rerun()
