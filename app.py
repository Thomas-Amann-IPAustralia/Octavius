import json
from pathlib import Path
import streamlit as st

from logic.lint import audit_text  # we'll create this next
from logic.docx_parser import parse_docx_to_hansel_markdown  # placeholder for now

st.set_page_config(page_title="Octavius", layout="wide")
st.title("Octavius (Hansel Web Port)")

# Load rules once into session state
if "rules" not in st.session_state:
    rules_path = Path("data/Trinity.json")
    with rules_path.open("r", encoding="utf-8") as f:
        st.session_state["rules"] = json.load(f)

if "text" not in st.session_state:
    st.session_state["text"] = ""

# Sidebar
st.sidebar.header("Controls")
mode = st.sidebar.radio("Input mode", ["Paste text", "Upload DOCX"])
show_raw_findings = st.sidebar.checkbox("Show raw findings JSON", value=True)

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
            st.success("DOCX parsed into Hansel-style semantic text.")
            st.text_area("Parsed text (read-only preview)", st.session_state["text"], height=250, disabled=True)
        except Exception as e:
            st.error(f"Failed to parse DOCX: {e}")

# Run linter
if st.button("Run audit") or st.session_state["text"]:
    text = st.session_state["text"]
    if text.strip():
        try:
            findings = audit_text(text=text, rules=st.session_state["rules"])
            st.subheader(f"Findings ({len(findings)})")

            for i, f in enumerate(findings, start=1):
                st.markdown(
                    f"**{i}.** `{f.get('rule_id', 'UNKNOWN')}` | "
                    f"chars **{f.get('start_char')}–{f.get('end_char')}**  \n"
                    f"{f.get('message', '')}"
                )

            if show_raw_findings:
                st.json(findings)
        except Exception as e:
            st.error(f"Linter error: {e}")
    else:
        st.info("Paste text or upload a DOCX to begin.")
