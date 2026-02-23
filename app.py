import json
import time
from pathlib import Path
import streamlit as st
import pandas as pd

from logic.lint import lint_text, get_spacy_status
from logic.docx_parser import parse_docx_to_hansel_markdown

st.set_page_config(page_title="Octavius", layout="wide")
st.title("Octavius (Hansel Web Port)")

# Load rules once into session state
if "rules" not in st.session_state:
    rules_path = Path("data/Trinity.json")
    try:
        with rules_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
            # Flatten the nested RuleSet structure into a single list of rules
            all_rules = []
            for ruleset in raw_data:
                for rule in ruleset.get("rules", []):
                    # Initialize session-only controls
                    rule["enabled"] = True
                    rule["severity_override"] = None
                    all_rules.append(rule)
            st.session_state["rules"] = all_rules
    except FileNotFoundError:
        st.error(f"Rules file not found at {rules_path}")
        st.session_state["rules"] = []
    except json.JSONDecodeError:
        st.error(f"Failed to decode JSON from {rules_path}")
        st.session_state["rules"] = []
    except Exception as e:
        st.error(f"Unexpected error loading rules: {e}")
        st.session_state["rules"] = []

# Session state defaults
if "text" not in st.session_state:
    st.session_state["text"] = ""

if "findings" not in st.session_state:
    st.session_state["findings"] = []

# Sidebar
st.sidebar.header("Controls")
mode = st.sidebar.radio("Input mode", ["Paste text", "Upload DOCX"])
show_raw_findings = st.sidebar.checkbox("Show raw findings JSON", value=True)

st.sidebar.divider()
st.sidebar.subheader("System Diagnostics")
spacy_loaded = get_spacy_status()
if spacy_loaded:
    st.sidebar.success("spaCy model loaded")
else:
    st.sidebar.error("spaCy model NOT loaded")

rule_count = len(st.session_state.get("rules", []))
st.sidebar.info(f"Rules loaded: {rule_count}")

if mode == "Upload DOCX":
    st.sidebar.caption("DOCX parsing is currently placeholder output for pipeline testing.")

tab_audit, tab_advanced = st.tabs(["Audit", "Advanced Mode"])

with tab_audit:
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
                start_time = time.perf_counter()
                findings = lint_text(text=text, rules=st.session_state["rules"])
                duration = time.perf_counter() - start_time

                st.session_state["findings"] = findings
                st.session_state["audit_duration"] = duration
            except Exception as e:
                st.error(f"Linter error: {e}")
                st.session_state["findings"] = []
        else:
            st.info("Paste text or upload a DOCX to begin.")
            st.session_state["findings"] = []
            st.session_state["audit_duration"] = 0

    # Findings display (persists across reruns)
    findings = st.session_state.get("findings", [])
    duration = st.session_state.get("audit_duration", 0)

    if findings:
        st.subheader(f"Findings ({len(findings)})")
        if duration > 0:
            st.caption(f"Audit completed in {duration:.3f} seconds")

        for i, f in enumerate(findings, start=1):
            severity = f.get('severity', 'info').upper()
            color = "red" if severity == "ERROR" else "orange" if severity == "WARN" else "blue"

            st.markdown(
                f"**{i}.** :{color}[{severity}] `{f.get('rule_id', 'UNKNOWN')}` | "
                f"chars **{f.get('start_char')}–{f.get('end_char')}**  \n"
                f"**Message:** {f.get('message', '')}"
            )
            if f.get('suggestion'):
                st.markdown(f"**Suggestion:** {f.get('suggestion')}")

        if show_raw_findings:
            st.json(findings)

with tab_advanced:
    st.header("Advanced Mode")

    st.subheader("Rule Browser")
    st.caption("Inspect, enable/disable, or override rule severities for this session.")

    # 1. Search/Filter
    search_query = st.text_input("Search rules (ID, Title, Message)", placeholder="Enter keyword...")

    # 2. Rule Browser (Table)
    rules_data = st.session_state["rules"]
    df_rules = pd.DataFrame(rules_data)

    # Reorder columns for better UI
    display_cols = ["enabled", "id", "severity", "severity_override", "category", "title", "message"]
    # Ensure all requested columns exist in the DF
    actual_cols = [c for c in display_cols if c in df_rules.columns]
    df_rules = df_rules[actual_cols]

    # Filter based on search
    if search_query:
        mask = df_rules.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
        df_rules = df_rules[mask]

    # Edit rules
    edited_df = st.data_editor(
        df_rules,
        column_config={
            "enabled": st.column_config.CheckboxColumn("Enabled", default=True),
            "severity_override": st.column_config.SelectboxColumn(
                "Override Severity",
                options=[None, "error", "warn", "info"],
                help="Override the default severity for this session"
            ),
            "severity": st.column_config.TextColumn("Default Severity", disabled=True),
            "id": st.column_config.TextColumn("ID", disabled=True),
            "category": st.column_config.TextColumn("Category", disabled=True),
            "title": st.column_config.TextColumn("Title", disabled=True),
            "message": st.column_config.TextColumn("Message", disabled=True),
        },
        disabled=["id", "severity", "category", "title", "message"],
        hide_index=True,
        use_container_width=True,
        key="rules_editor_ui"
    )

    # 3. Apply changes back to session state
    if st.button("Apply changes to session"):
        # Map IDs to indices in st.session_state["rules"]
        id_to_idx = {r["id"]: i for i, r in enumerate(st.session_state["rules"])}
        # We use edited_df which contains all rows if not filtered, OR filtered rows.
        # But wait, if it's filtered, we only see a subset.
        # st.data_editor when filtered only returns the filtered subset.
        # So we update only what's in edited_df.
        for _, row in edited_df.iterrows():
            idx = id_to_idx.get(row["id"])
            if idx is not None:
                st.session_state["rules"][idx]["enabled"] = row["enabled"]
                st.session_state["rules"][idx]["severity_override"] = row["severity_override"] if row["severity_override"] else None
        st.success(f"Updated {len(edited_df)} rules in session state.")

    st.divider()
    st.subheader("Regex Sandbox")
    st.caption("Test a custom regex pattern against sample text to see if it matches as expected.")

    sandbox_text = st.text_area("Sandbox Test Text", height=150, placeholder="Enter text to test against...", key="sb_text")
    sandbox_regex = st.text_input("Custom Regex Pattern", placeholder="e.g. \\b(Apple|Orange)\\b", key="sb_regex")

    if st.button("Run Sandbox Test"):
        if sandbox_regex and sandbox_text:
            try:
                import re
                matches = list(re.finditer(sandbox_regex, sandbox_text, re.MULTILINE))
                if matches:
                    st.success(f"Found {len(matches)} matches!")
                    for i, m in enumerate(matches, 1):
                        st.markdown(f"**Match {i}:** `{m.group()}` (chars {m.start()}–{m.end()})")
                else:
                    st.info("No matches found.")
            except re.error as e:
                st.error(f"Invalid regex: {e}")
        else:
            st.warning("Please provide both a pattern and test text.")
