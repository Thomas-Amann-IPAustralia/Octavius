# Octavius: Technical Documentation

## 1. Executive Summary

Octavius is a rule-driven content auditing web application designed to enforce the Australian Public Service (APS) Style Guide. It is a web-based evolution of a CLI tool called "Hansel", transforming its core auditing logic into an interactive, "Grammarly-style" application.

### Active User Needs (Current Focus)

The system's current architecture is built to support:

1. **Run rules against content (Simple Mode):** Auditing pasted text, uploaded `.docx` files, and (eventually) LLM-generated content.
2. **Modify the applied rules (Advanced Mode):** Dynamically tweaking the active rule set in the browser.

*(Future states will include GenAI authoring and machine-readable JSON-LD conversion).*

---

## 2. System Architecture: The "Streamlit Sandwich"

Octavius utilizes a "Hybrid" architecture that bridges Python's data-processing strengths with React's rich interactivity. It is divided into three primary layers:

### A. The Controller (Streamlit - `app.py`)

Streamlit serves as the backend and the application wrapper. It handles:

* **State Management:** Loading the massive APS rule set from `data/Trinity.json` into `st.session_state['rules']` upon initialization.
* **Routing & UI Controls:** Managing the sidebar, input modes (Paste vs. DOCX upload), and switching between Simple and Advanced modes.
* **Data Bridging:** Passing text from the frontend to the Python logic layer, and sending the resulting audit "findings" back to the frontend.

### B. The Logic Layer (Python - `logic/lint.py` & `logic/docx_parser.py`)

This is the "Brain" of the application, running on the server.

* **The Auditing Engine (`lint.py`):** A hybrid NLP and Regex linter. It receives raw text and the active rule set.
* **Regex Matching:** Fast pattern recognition for standard rules (e.g., catching incorrect date formats or banned acronyms).
* **Heuristic Analysis:** For complex grammatical rules (like passive voice detection), it relies on `spaCy` (`en_core_web_sm`) to perform dependency parsing.
* **Precise Mapping:** Crucially, the linter calculates exact character indices (`start_char`, `end_char`) for every violation, which is required by the frontend editor.


* **DOCX Parsing (`docx_parser.py`):** *(Currently a placeholder)* Designed to parse MS Word documents and inject "Semantic Tags" (e.g., `__SEMANTIC_H1_START__`) to preserve structural context for the linter.

### C. The Visual Editor (React - `frontend/src/editor.tsx`)

Because standard Streamlit text areas cannot render multi-color highlights, Octavius uses a Custom React Component built with `streamlit-component-lib`.

* **Input:** It receives the raw `text` and an array of `highlights` (error objects containing start/end indices and messages) from Python.
* **Rendering:** It iterates through the text, slicing it based on the highlight indices, and wraps offending strings in styled HTML `<span>` tags (red underlines). It also applies simple tooltips so users can hover to see the specific APS rule violation.
* **Bi-directional Communication:** On every keystroke, the React component uses `Streamlit.setComponentValue(newText)` to send the updated text back to the Streamlit backend for re-auditing.

---

## 3. The Rules Engine (`Trinity.json`)

The core behavior of the application is dictated by `data/Trinity.json`. This is a hierarchical dataset containing hundreds of rules categorized by Book, Chapter, and RuleSet.

**Rule Schema:**

* `id`: Unique identifier (e.g., `APS-GPC-Partsofsentences-H-009`).
* `category`: Either `regex` (strict string matching) or `heuristic` (triggers complex Python functions in `lint.py`).
* `severity`: `error`, `warn`, or `info`.
* `pattern`: The raw regex string (if applicable).
* `message`: The specific guidance shown to the user in the tooltip.

Because `app.py` loads this JSON into Streamlit's Session State, the system is designed to allow real-time modification of these rules (User Need 2).

---

## 4. The "No-Install" Development Loop

Octavius is developed entirely in the cloud, requiring zero local environment setup or local code execution. Coding agents and developers must strictly adhere to this workflow:

1. **Edit on GitHub:** Open the code files directly on GitHub.com. Use the built-in web editor by pressing the `.` (period) key on your keyboard while viewing the repository. This opens a "lite" version of VS Code directly in your browser.
2. **Commit:** Save your changes and commit them directly to the `main` branch.
3. **Auto-Deploy:** Streamlit Community Cloud continuously monitors the repository. The moment a new commit is detected, it automatically pulls the code, installs any updated dependencies from `requirements.txt` / `package.json`, and restarts the application.
4. **View:** Refresh the live application URL ([https://0ctavius.streamlit.app/](https://0ctavius.streamlit.app/)) to view and test the results of your code changes.

*(Note: Because of this loop, print statements or console errors must be debugged either through the Streamlit UI or the Streamlit Cloud dashboard logs).*

---

## 5. Repository Structure

This clearly outlines the separation of concerns between the Streamlit root (app.py), the Python auditing engine (logic/), the React custom component (frontend/), and the configuration files (data/).

Octavius-main/
├── app.py                       # Main Streamlit controller and entry point
├── README.md                    # The primary technical documentation (you are here!)
├── requirements.txt             # Python dependencies for the Streamlit backend
├── data/
│   └── Trinity.json             # The core JSON ruleset containing APS guidelines
├── frontend/                    # Custom React component for the visual editor
│   ├── folderbuilder            # Utility script/binary for frontend scaffolding
│   ├── package.json             # Node.js dependencies for the React frontend
│   ├── public/
│   │   └── index.html           # HTML template for the React component
│   └── src/
│       ├── editor.tsx           # Main React component handling text and highlights
│       ├── index.tsx            # React application entry point
│       └── style.css            # Custom styling for the editor and tooltips
└── logic/                       # Python backend logic and processing
    ├── __init__.py
    ├── docx_parser.py           # Parser for MS Word documents and semantic tagging
    └── lint.py                  # The auditing engine (NLP and Regex logic)
