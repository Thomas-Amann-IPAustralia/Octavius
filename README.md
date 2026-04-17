# Octavius

A plain-language linter for Australian Public Service (APS) content.

Paste a block of text and Octavius highlights style violations inline, listing each finding with a suggested fix. The rulebook contains **3 114 rules** extracted from the Australian Government Style Manual.

> **Architecture:** Python + spaCy NLP backend (FastAPI), vanilla HTML/JS single-page frontend. Rule content is sourced from the Australian Government Style Manual and published to `published/rulebook.parquet` by a six-phase GitHub Actions pipeline.

---

## Getting started

**Prerequisites:** Python 3.9+

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd Octavius

# 2. Install dependencies (includes the spaCy model)
pip install -r requirements.txt

# 3. Start the FastAPI backend
uvicorn main:app --reload
# API available at http://localhost:8000

# 4. Open index.html in a browser
```

The frontend (`index.html`) talks to the backend at the same origin in production, or at `http://localhost:8000` in development. No build step is required.

### Legacy Streamlit app

```bash
streamlit run app.py
# Opens at http://localhost:8501
```

---

## Running tests

```bash
pytest tests/ -v
```

---

## Project structure

```
Octavius/
├── main.py                   # FastAPI backend — /groups and /check endpoints
├── index.html                # Standalone vanilla HTML/JS frontend
├── render.yaml               # Render.com deployment config (uvicorn, Python 3.11)
├── app.py                    # Legacy Streamlit UI
├── requirements.txt          # Python dependencies
├── logic/
│   ├── engine.py             # lint_text() — runs rules against a spaCy Doc
│   └── rules.py              # RULES list + individual rule check functions
├── frontend/                 # Legacy React component (Streamlit)
│   ├── src/
│   │   ├── OctaviusEditor.tsx        # Root React component (state, layout)
│   │   ├── components/               # TextEditor, FindingsPanel, FindingCard, RulesPanel, etc.
│   │   ├── hooks/useHighlights.ts    # Text segmentation for inline highlights
│   │   └── types.ts                  # Shared TypeScript types
│   └── build/                        # Compiled component (loaded by Streamlit)
├── src/                      # Rulebook creation pipeline (Phases 1–6)
│   ├── scrape.py             # Phase 1 — mirror Style Manual to content/
│   ├── extract_rules.py      # Phase 2 — LLM batch: page markdown → JSONL rules
│   ├── generate_code.py      # Phase 3 — LLM batch: rule → trigger_code
│   ├── run_tests.py          # Phase 4 — execute trigger_code, record pass/fail
│   ├── correct_rules.py      # Phase 5 — LLM batch: fix failing rules
│   └── publish.py            # Phase 6 — JSONL → published/rulebook.parquet
├── published/
│   ├── rulebook.parquet      # Published rulebook (3 114 rules)
│   └── rulebook_metadata.json# Counts by taxonomy, test result, etc.
├── rules_working_draft.jsonl # Working copy of all rules (same schema as parquet)
├── content/                  # Scraped Style Manual pages (markdown)
├── library_of_rules/         # Reference rule content from the Style Manual
│   ├── Grammar, Punctuation and conventions/
│   ├── Accessible and inclusive content/
│   ├── Writing and designing content/
│   ├── Structuring content/
│   ├── Referencing and attribution/
│   ├── Handbook/
│   └── SiteMap.md            # Navigation index for the rule library
├── tests/
│   └── test_engine.py        # Unit tests for the linting engine
└── archive/                  # Previous implementations (reference only)
```

---

## Frontend (`index.html`)

The frontend is a self-contained HTML file — no framework, no build step.

**Layout:** three-pane split

| Pane | Contents |
|------|----------|
| Editor | `<textarea>` overlaid by a backdrop `<div>` that renders coloured `<span>` highlights in exact typographic alignment |
| Issues tab | Filterable finding cards (error / warn / info) with rule ID, message, and suggestion |
| Rules tab | Rule-group checkboxes with enabled/total counts; selections persist in `localStorage` |

**Key behaviours:**
- Linting is debounced 300 ms after each keystroke; in-flight requests are aborted before a new one fires
- Clicking a highlight scrolls to and activates the corresponding finding card, and vice versa
- Hovering over a highlight shows a tooltip with rule ID, severity, message, and suggestion

**API endpoints used:**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/groups` | Returns rule categories with counts for the Rules tab |
| `POST` | `/check` | Accepts `{text, rule_groups}`, returns findings |

---

## Parquet / JSONL schema

`published/rulebook.parquet` and `rules_working_draft.jsonl` share the same column schema. This is the canonical shape of a rule record throughout the pipeline.

| Column | Type | Description |
|--------|------|-------------|
| `rule_id` | string | Unique identifier, e.g. `"grammar--active-voice-001"` |
| `source_url` | string | Style Manual page the rule was extracted from |
| `source_file` | string | Local mirrored path, e.g. `"content/grammar/active-voice.md"` |
| `rule_summary` | string | One-sentence plain-English summary of the rule |
| `rule_detail` | string | Longer explanation used in the UI message |
| `taxonomy` | string | Detection family: `lookup` \| `regex` \| `structural` \| `semantic` \| `contextual` \| `discretionary` \| `multi-modal` |
| `discretionary_flag` | bool | `true` if the rule is advisory / not enforced |
| `method` | string | Concrete detection method (mirrors taxonomy) |
| `requires` | list[string] | Rule IDs that must fire first (dependency list) |
| `method_notes` | string | Notes on the detection approach written during Phase 3 |
| `trigger_code` | string | Executable Python: `def check_rule(text, lookup_list) -> list[dict]` |
| `ui_flag` | string | Message displayed in the UI when the rule fires |
| `test_fire` | list[string] | Strings that **must** trigger the rule (Phase 4 positive tests) |
| `test_no_fire` | list[string] | Strings that **must not** trigger the rule (Phase 4 negative tests) |
| `lookup_list` | list[string] | Terms to match for `lookup`-taxonomy rules (empty for other methods) |
| `test_result` | string | `"pass"` \| `"fail"` \| `"skip"` \| `"frozen"` |
| `error_log` | string | Error or failure detail from Phase 4 / Phase 5 |
| `correction_model` | string | Model used to correct the rule in Phase 5, if applicable |
| `extracted_at` | string | ISO 8601 timestamp — Phase 2 extraction |
| `code_generated_at` | string | ISO 8601 timestamp — Phase 3 code generation |
| `test_run_at` | string | ISO 8601 timestamp — Phase 4 test execution |

**Taxonomy distribution (current published rulebook):**

| Taxonomy | Count |
|----------|-------|
| semantic | 1 497 |
| lookup | 529 |
| structural | 504 |
| regex | 197 |
| contextual | 191 |
| discretionary | 188 |
| multi-modal | 8 |
| **Total** | **3 114** |

---

## How rules work (logic layer)

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

## Rulebook creation pipeline

The `src/` directory contains the six-phase GitHub Actions pipeline that builds
the rulebook from the Australian Government Style Manual. The full design lives
in `CLAUDE_Octavius Rulebook Creation Pipeline.md`.

| Phase | File | Role |
|-------|------|------|
| 1 | `src/scrape.py` | Mirror Style Manual pages to `content/` as markdown |
| 2 | `src/extract_rules.py` | LLM batch: page markdown → JSONL rule records |
| 3 | `src/generate_code.py` | LLM batch: rule record → executable `trigger_code` |
| 4 | `src/run_tests.py` | Execute `trigger_code` against `test_fire` / `test_no_fire` strings |
| 5 | `src/correct_rules.py` | LLM batch: rewrite failing rules |
| 6 | `src/publish.py` | Validated JSONL → `published/rulebook.parquet` |

**Phase 1 — scraping notes:**

- Tries the sitemap with `requests` + the `OctaviusRulebookBot/1.0` User-Agent first, and falls back to Selenium if the WAF drops the request (as `stylemanual.gov.au` started doing in April 2026). Page fetches always use Selenium.
- Accepts either raw XML or the XSLT-rendered HTML table that browsers receive for `/sitemap.xml`. Both shapes flow through the same `parse_sitemap` entry point.
- Aborts with a clear error if parsing yields zero URLs, so a misconfigured `SITEMAP_URL` is surfaced immediately.
- `SITEMAP_URL` defaults to `https://www.stylemanual.gov.au/sitemap.xml` and can be overridden via a repository variable for testing.

---

## Contributing

Contributions are welcome. The most impactful place to start is adding new rules to `logic/rules.py` — see the section above for how rules are structured.

Please run `pytest tests/ -v` before opening a pull request.
