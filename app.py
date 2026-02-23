import json
from pathlib import Path
import streamlit as st

from logic.lint import lint_text  # we'll create this next
from logic.docx_parser import parse_docx_to_hansel_markdown  # placeholder for now

st.set_page_config(page_title="Octavius", layout="wide")
st.title("Octavius (Hansel Web Port)")

# Load rules once into session state
if "rules" not in st.session_state:
    rules_path = Path("data/Trinity.json")
    with rules_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)
        # Flatten the nested RuleSet structure into a single list of rules
        all_rules = []
        for ruleset in raw_data:
            all_rules.extend(ruleset.get("rules", []))
        st.session_state["rules"] = all_rules

# Session state defaults
if "text" not in st.session_state:
    st.session_state["text"] = ""

if "findings" not in st.session_state:
    st.session_state["findings"] = []

# Sidebar
st.sidebar.header("Controls")
mode = st.sidebar.radio("Input mode", ["Paste text", "Upload DOCX"])
show_raw_findings = st.sidebar.checkbox("Show raw findings JSON", value=True)

if mode == "Upload DOCX":
    st.sidebar.caption("DOCX parsing is currently placeholder output for pipeline testing.")

# Input
if mode == "Paste text":
    st.session_state["text"] = st.text_area(
        "Drafting area",
        value=st.session_state["text"],
        height=300,
        placeholder="Paste APS-style content here..."
    )
else:
    uploaded = st.file_uploader("Upload a .docx file", type=["docx"])
    if uploaded is not None:
        try:
            st.session_state["text"] = parse_docx_to_hansel_markdown(uploaded)
            st.info("DOCX upload received. Placeholder parser is active (not final Hansel semantic parsing yet).")
            st.text_area(
                "Parser output preview (placeholder)",
                st.session_state["text"],
                height=250,
                disabled=True
            )
        except Exception as e:
            st.error(f"Failed to parse DOCX: {e}")

# Run linter (button-trigger only; no automatic rerun on every text change)
run_audit = st.button("Run audit")

if run_audit:
    text = st.session_state["text"]
    if text.strip():
        try:
            findings = lint_text(text=text, rules=st.session_state["rules"])
            st.session_state["findings"] = findings
        except Exception as e:
            st.error(f"Linter error: {e}")
            st.session_state["findings"] = []
    else:
        st.info("Paste text or upload a DOCX to begin.")
        st.session_state["findings"] = []

# Findings display (persists across reruns)
findings = st.session_state.get("findings", [])
if findings:
    st.subheader(f"Findings ({len(findings)})")

    for i, f in enumerate(findings, start=1):
        st.markdown(
            f"**{i}.** `{f.get('rule_id', 'UNKNOWN')}` | "
            f"chars **{f.get('start_char')}–{f.get('end_char')}**  \n"
            f"{f.get('message', '')}"
        )

    if show_raw_findings:
        st.json(findings)
