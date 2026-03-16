# Octavius

A plain-language linter for Australian Public Service (APS) content, built with Streamlit and spaCy.

Paste a block of text, click **Run audit**, and Octavius highlights style violations inline and lists each finding with a suggested fix.

> **Current scope:** This is a *vertical-slice MVP* focused on a single rule — passive voice detection — to validate the core architecture before the rule set is expanded.

---

## Getting started

**Prerequisites:** Python 3.9+

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd Octavius

# 2. Install dependencies (includes the spaCy model)
pip install -r requirements.txt

# 3. Start the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Running tests

```bash
pytest tests/ -v
```

---

## Project structure

```
Octavius/
├── app.py              # Streamlit UI — page layout, session state, result rendering
├── requirements.txt    # Python dependencies
├── logic/
│   ├── engine.py       # lint_text() — runs rules against a spaCy Doc
│   └── rules.py        # RULES list + individual rule check functions
├── tests/
│   └── test_engine.py  # Unit tests for the linting engine
└── archive/            # Previous implementations (reference only)
```

---

## How rules work

Each rule in `logic/rules.py` is a plain dict:

```python
{
    "id": "PASSIVE-VOICE-001",
    "title": "Passive voice detected",
    "message": "Passive voice can reduce clarity. Consider rewriting in active voice.",
    "severity": "warn",   # "error" | "warn" | "info"
    "suggestion": None,
    "check": check_passive_voice,   # fn(doc: spacy.Doc) -> list[dict]
}
```

The `check` function receives a spaCy `Doc` and returns a list of findings, each with `start_char` and `end_char` (character offsets into the original text) plus an optional `suggestion` string.

To add a new rule:

1. Write a `check_*` function in `logic/rules.py` that analyses the `Doc` and returns findings.
2. Append a rule dict to `RULES`.

The engine and UI pick it up automatically — no other changes needed.

---

## Architecture

```
User input (Streamlit text area)
        │
        ▼
   app.py  ──►  logic/engine.lint_text(text, RULES)
                        │
                        ▼
               spaCy NLP pipeline
                        │
                        ▼
           logic/rules.check_*(doc)  ×N rules
                        │
                        ▼
            Findings (start_char, end_char, message, …)
                        │
                        ▼
        Annotated display + per-finding detail cards
```

---

## Contributing

Contributions are welcome. The most impactful place to start is adding new rules to `logic/rules.py` — see the section above for how rules are structured.

Please run `pytest tests/ -v` before opening a pull request.
