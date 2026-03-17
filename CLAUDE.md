# CLAUDE.md

## Project overview

Octavius is a plain-language linter for Australian Public Service (APS) content. It analyzes text for style violations (e.g. passive voice) and highlights them inline with suggestions and detailed findings.

The stack is:
- **Backend:** Python + spaCy NLP + Streamlit
- **Frontend:** React 18 + TypeScript + Tailwind CSS (embedded as a Streamlit custom component)

This is a vertical-slice MVP. The passive voice rule is the proof-of-concept; the architecture is designed for easy rule expansion.

---

## Commands

### Run the app
```bash
streamlit run app.py
# Opens at http://localhost:8501
```

### Run tests
```bash
pytest tests/ -v
```

### Install dependencies
```bash
pip install -r requirements.txt
```

### Build the React component (only needed if frontend/ is modified)
```bash
cd frontend && npm run build
```

---

## Architecture

```
User input (Streamlit text area)
        │
        ▼
   app.py  ──►  logic/engine.lint_text(text, RULES)
                        │
                        ▼
               spaCy NLP pipeline (en_core_web_sm)
                        │
                        ▼
           logic/rules.check_*(doc)  ×N rules
                        │
                        ▼
            Findings (start_char, end_char, message, …)
                        │
                        ▼
        React component (inline highlights + findings panel)
```

The React component lives in `frontend/` and is compiled to `frontend/build/`. Streamlit loads it as a custom component and passes findings from Python via props.

---

## Key files

| File | Role |
|------|------|
| `app.py` | Streamlit entry point — layout, session state, passing data to React |
| `logic/engine.py` | `lint_text(text, rules)` — runs all rules against a spaCy Doc |
| `logic/rules.py` | `RULES` list + individual `check_*` functions |
| `tests/test_engine.py` | Pytest unit tests for the linting engine |
| `frontend/src/OctaviusEditor.tsx` | Root React component |
| `frontend/src/components/` | TextEditor, FindingsPanel, FindingCard, etc. |
| `frontend/src/types.ts` | Shared TypeScript types (Finding, Rule) |

---

## Adding a new rule

1. Write a `check_*` function in `logic/rules.py`:
   ```python
   def check_my_rule(doc) -> list[dict]:
       findings = []
       # analyse doc, append dicts with start_char, end_char, suggestion
       return findings
   ```
2. Append a rule dict to `RULES`:
   ```python
   {
       "id": "MY-RULE-001",
       "title": "Short title",
       "message": "Explanation shown to the user.",
       "severity": "warn",   # "error" | "warn" | "info"
       "suggestion": None,   # or a static suggestion string
       "check": check_my_rule,
   }
   ```

The engine and UI pick it up automatically — no other changes needed.

---

## Testing guidance

- Tests live in `tests/test_engine.py` and use pytest.
- Run `pytest tests/ -v` before opening a pull request.
- Test new rules by asserting that `lint_text` returns the expected findings for known inputs.
- The `archive/` directory contains previous implementations for reference only — do not modify it.

---

## Code style

**Python:** Use type hints (TypedDict, list, Optional). Follow existing module structure. No linter is configured; match the style of surrounding code.

**TypeScript:** Strict mode is enabled. Use the existing `Finding` and `Rule` types from `types.ts`. Style with Tailwind utility classes.
