import streamlit as st
import json
import os

st.set_page_config(page_title="Octavius", layout="wide")

st.title("Octavius: APS Style Auditor")

# 1. Load Rules (Phase 1 Check)
try:
    with open('data/Trinity.json', 'r') as f:
        rules = json.load(f)
    st.success(f"✅ System Online: Loaded {len(rules)} rule sets from Trinity.json")
    
    # Store rules in session state as requested in the brief
    if 'rules' not in st.session_state:
        st.session_state['rules'] = rules

except FileNotFoundError:
    st.error("❌ Critical Error: Trinity.json not found in /data folder.")

# 2. Input Area
text_input = st.text_area("Paste text to audit:", height=300)

if st.button("Audit Text"):
    st.info("The linter logic is not connected yet (coming in Phase 2!)")
    st.write("You wrote:", text_input)
