import streamlit as st
import streamlit.components.v1 as components
import json
import os
import sys

# Add logic folder to path
sys.path.append('.')
from logic.lint import lint_text

st.set_page_config(page_title="Octavius", layout="wide")
st.title("Octavius: APS Style Auditor")

# --- 1. Load Rules ---
if 'rules' not in st.session_state:
    try:
        with open('data/Trinity.json', 'r') as f:
            st.session_state['rules'] = json.load(f)
    except FileNotFoundError:
        st.error("❌ Trinity.json missing.")
        st.stop()

# --- 2. Setup the Frontend Component ---
# In development (local), we would use url="http://localhost:3000"
# In production (web), we point to the built static files
# Since we haven't built it yet, we will put a placeholder here for now.
COMPONENT_PATH = os.path.join(os.path.dirname(__file__), "frontend", "build")

def octavius_editor(text, highlights, key=None):
    # This function declares the custom component
    if os.path.exists(COMPONENT_PATH):
        # Load the built component
        component = components.declare_component("octavius_editor", path=COMPONENT_PATH)
        return component(text=text, highlights=highlights, key=key, default=text)
    else:
        # Fallback if build is missing (Phase 3 transition state)
        st.warning("⚠️ Frontend not built. Using standard text area.")
        return st.text_area("Input Text", value=text, key=key, height=300)

# --- 3. App Logic ---

# Initialize text state
if 'doc_text' not in st.session_state:
    st.session_state['doc_text'] = "The form was submitted. The large red car."

# Run Linter
findings = lint_text(st.session_state['doc_text'], st.session_state['rules'])

# Display Component
# The component takes 'text' and 'highlights' as input
# It returns the 'new_text' whenever the user types
new_text = octavius_editor(
    text=st.session_state['doc_text'], 
    highlights=findings,
    key="editor"
)

# Update state if text changed
if new_text != st.session_state['doc_text']:
    st.session_state['doc_text'] = new_text
    st.rerun()

# Debug Area
with st.expander("Debug: Raw Findings"):
    st.json(findings)
