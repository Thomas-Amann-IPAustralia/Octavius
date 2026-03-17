"""Octavius — plain-language linter with React visual editor."""

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

from logic.engine import get_spacy_status, lint_text
from logic.rules import RULES

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(page_title="Octavius", layout="wide")

# ── Register the custom React component ──────────────────────────────
# Use an absolute path so the component loads correctly regardless of
# the working directory (important on Streamlit Community Cloud).
_BUILD_DIR = Path(__file__).parent / "frontend" / "build"

_octavius_editor = components.declare_component(
    "octavius_editor",
    path=str(_BUILD_DIR),
)


def st_octavius_editor(
    text: str,
    findings: list,
    rules: list,
    key: str | None = None,
) -> dict | None:
    """Render the React visual editor and return the latest value dict."""
    return _octavius_editor(
        text=text,
        findings=findings,
        rules=rules,
        key=key,
        default=None,
    )


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
