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
            for rs_block in raw_data:
                book = rs_block.get("Book", "Unknown Book")
                chapter = rs_block.get("Chapter", "Unknown Chapter")
                ruleset_name = rs_block.get("RuleSet", "Unknown RuleSet")
                for rule in rs_block.get("rules", []):
                    # Inject hierarchical context
                    rule["book"] = book
                    rule["chapter"] = chapter
                    rule["ruleset"] = ruleset_name
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

# Shared Input Area
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

tab_audit, tab_advanced = st.tabs(["Audit", "Advanced Mode"])

with tab_audit:
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

    st.subheader("Hierarchical Rule Controls")
    all_rules_df = pd.DataFrame(st.session_state["rules"])

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_books = st.multiselect("Filter by Book", options=sorted(all_rules_df["book"].unique()))

    filtered_chapters_df = all_rules_df[all_rules_df["book"].isin(selected_books)] if selected_books else all_rules_df
    with col2:
        selected_chapters = st.multiselect("Filter by Chapter", options=sorted(filtered_chapters_df["chapter"].unique()))

    filtered_rulesets_df = filtered_chapters_df[filtered_chapters_df["chapter"].isin(selected_chapters)] if selected_chapters else filtered_chapters_df
    with col3:
        selected_rulesets = st.multiselect("Filter by RuleSet", options=sorted(filtered_rulesets_df["ruleset"].unique()))

    # Calculate what would be filtered
    bulk_df = all_rules_df.copy()
    if selected_books:
        bulk_df = bulk_df[bulk_df["book"].isin(selected_books)]
    if selected_chapters:
        bulk_df = bulk_df[bulk_df["chapter"].isin(selected_chapters)]
    if selected_rulesets:
        bulk_df = bulk_df[bulk_df["ruleset"].isin(selected_rulesets)]

    col_b1, col_b2, _ = st.columns([1, 1, 4])
    with col_b1:
        if st.button("Enable All Filtered", use_container_width=True):
            ids_to_enable = set(bulk_df["id"])
            for r in st.session_state["rules"]:
                if r["id"] in ids_to_enable:
                    r["enabled"] = True
            st.success(f"Enabled {len(ids_to_enable)} rules.")
            st.rerun()
    with col_b2:
        if st.button("Disable All Filtered", use_container_width=True):
            ids_to_disable = set(bulk_df["id"])
            for r in st.session_state["rules"]:
                if r["id"] in ids_to_disable:
                    r["enabled"] = False
            st.success(f"Disabled {len(ids_to_disable)} rules.")
            st.rerun()

    st.subheader("Rule Browser")
    st.caption("Inspect, enable/disable, or override rule severities for this session.")

    # 1. Search/Filter
    search_query = st.text_input("Search rules (ID, Title, Message)", placeholder="Enter keyword...")

    # 2. Rule Browser (Table)
    rules_data = st.session_state["rules"]
    df_rules = pd.DataFrame(rules_data)

    # Apply hierarchical filters to the Rule Browser table as well
    if selected_books:
        df_rules = df_rules[df_rules["book"].isin(selected_books)]
    if selected_chapters:
        df_rules = df_rules[df_rules["chapter"].isin(selected_chapters)]
    if selected_rulesets:
        df_rules = df_rules[df_rules["ruleset"].isin(selected_rulesets)]

    # Reorder columns for better UI
    display_cols = ["enabled", "book", "chapter", "ruleset", "id", "severity", "severity_override", "category", "title", "message"]
    # Ensure all requested columns exist in the DF
    actual_cols = [c for c in display_cols if c in df_rules.columns]
    df_rules = df_rules[actual_cols]

    # Filter based on search
    if search_query:
        mask = df_rules.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
        df_rules = df_rules[mask]

    # Edit rules
    # We use the return value to update session state automatically on next rerun
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
            "book": st.column_config.TextColumn("Book", disabled=True),
            "chapter": st.column_config.TextColumn("Chapter", disabled=True),
            "ruleset": st.column_config.TextColumn("RuleSet", disabled=True),
            "id": st.column_config.TextColumn("ID", disabled=True),
            "category": st.column_config.TextColumn("Category", disabled=True),
            "title": st.column_config.TextColumn("Title", disabled=True),
            "message": st.column_config.TextColumn("Message", disabled=True),
        },
        disabled=["book", "chapter", "ruleset", "id", "severity", "category", "title", "message"],
        hide_index=True,
        use_container_width=True,
        key="rules_editor"
    )

    # 3. Apply changes back to session state
    # We do this automatically by checking for changes in st.session_state["rules_editor"]
    if "rules_editor" in st.session_state:
        edits = st.session_state["rules_editor"].get("edited_rows", {})
        if edits:
            # Map IDs to session state rules for efficient update
            id_to_rule = {r["id"]: r for r in st.session_state["rules"]}
            for row_idx, changes in edits.items():
                rule_id = df_rules.iloc[row_idx]["id"]
                rule = id_to_rule.get(rule_id)
                if rule:
                    if "enabled" in changes:
                        rule["enabled"] = changes["enabled"]
                    if "severity_override" in changes:
                        rule["severity_override"] = changes["severity_override"] if changes["severity_override"] else None
            # No st.rerun here to avoid infinite loop; it will take effect on next interaction.

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
