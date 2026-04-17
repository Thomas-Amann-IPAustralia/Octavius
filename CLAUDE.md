# CLAUDE.md

## Project overview

Octavius is a plain-language linter for Australian Public Service (APS) content. It analyzes text for style violations (e.g. passive voice) and highlights them inline with suggestions and detailed findings.

The stack is:
- **Backend:** Python + spaCy NLP + FastAPI (primary) / Streamlit (legacy)
- **Frontend:** Vanilla HTML/JS single-page app (`index.html`) served by FastAPI (primary) / React 18 + TypeScript + Tailwind CSS embedded as a Streamlit custom component (legacy)
- **Rulebook:** 3 114 rules published to `published/rulebook.parquet` by a six-phase GitHub Actions pipeline

This is a vertical-slice MVP. The passive voice rule is the proof-of-concept; the architecture is designed for easy rule expansion.

---

## Commands

### Run the app (FastAPI — primary)
```bash
uvicorn main:app --reload
# API at http://localhost:8000
# Open index.html in a browser pointing to http://localhost:8000
```

### Run the app (Streamlit — legacy)
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

### Primary (FastAPI + vanilla JS)

```
User types in index.html (300 ms debounce)
        │
        ▼  POST /check  {text, rule_groups}
   main.py  ──►  logic/engine.lint_text(text, active_rules)
                        │
                        ▼
               spaCy NLP pipeline (en_core_web_sm)
                        │
                        ▼
           logic/rules.check_*(doc)  ×N rules
                        │
                        ▼
     Findings [{rule_id, group, message, start, end, severity, suggestion}]
                        │
                        ▼
       index.html — overlay highlights + findings panel + rule-group toggles
```

`main.py` also exposes `GET /groups` which returns the distinct rule categories and their counts so the frontend can render the filter checkboxes.

### Legacy (Streamlit)

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
| `main.py` | FastAPI entry point — `/groups` and `/check` endpoints |
| `index.html` | Standalone vanilla HTML/JS frontend (861 LOC) |
| `render.yaml` | Render.com deployment config (uvicorn, Python 3.11) |
| `app.py` | Legacy Streamlit entry point — layout, session state, passing data to React |
| `logic/engine.py` | `lint_text(text, rules)` — runs all rules against a spaCy Doc |
| `logic/rules.py` | `RULES` list + individual `check_*` functions |
| `tests/test_engine.py` | Pytest unit tests for the linting engine |
| `frontend/src/OctaviusEditor.tsx` | Root React component (legacy) |
| `frontend/src/components/` | TextEditor, FindingsPanel, FindingCard, RulesPanel, StatsHeader, SeverityBadge, Tooltip |
| `frontend/src/hooks/useHighlights.ts` | Slices text into plain/highlighted segments |
| `frontend/src/types.ts` | Shared TypeScript types (Finding, RuleMeta, ComponentArgs) |
| `library_of_rules/` | Reference rule content from the Australian Government Style Manual |
| `library_of_rules/SiteMap.md` | Navigation index for the rule library |
| `library_of_rules/Octavius_Rulebook_Column_Reference.docx` | Column reference for rule authoring |
| `published/rulebook.parquet` | Published rulebook — 3 114 rules (see schema below) |
| `published/rulebook_metadata.json` | Counts by taxonomy, test result, etc. |

---

## Frontend (`index.html`)

The standalone frontend is a single HTML file with embedded CSS and JavaScript. No build step is required.

**Layout:** three-pane split
- **Editor pane** — `<textarea>` overlaid by a `<div>` backdrop that renders coloured `<span>` highlights in exact typographic alignment
- **Issues tab** — filterable list of finding cards (error / warn / info), each showing rule ID, message, and suggestion
- **Rules tab** — rule-group checkboxes with enabled/total counts; selections persist in `localStorage`

**Key behaviours:**
- Linting is debounced 300 ms after each keystroke; in-flight requests are aborted before a new one fires
- Clicking a highlight in the editor scrolls to and activates the corresponding finding card, and vice versa
- Hovering over a highlight shows a tooltip with rule ID, severity, message, and suggestion
- The `API_BASE` constant at the top of the script (defaults to `""`, i.e. same origin) can be changed for local development

**Severity colour scheme:**

| Severity | Highlight colour | Badge colour |
|----------|-----------------|--------------|
| `error`  | Rose            | Rose         |
| `warning`| Amber           | Amber        |
| `info`   | Violet          | Violet       |

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

The parquet file is written by `src/publish.py` using PyArrow with an explicit schema; the JSONL file is the line-delimited JSON equivalent written by `src/run_tests.py` and `src/correct_rules.py`.

**Taxonomy distribution (current published rulebook, 3 114 rules):**

| Taxonomy | Count |
|----------|-------|
| semantic | 1 497 |
| lookup | 529 |
| structural | 504 |
| regex | 197 |
| contextual | 191 |
| discretionary | 188 |
| multi-modal | 8 |

---

## Rule library (`library_of_rules/`)

The `library_of_rules/` directory contains reference content sourced from the Australian Government Style Manual. It is organised by topic and provides the authoritative source material for rules implemented in `logic/rules.py`.

```
library_of_rules/
├── Grammar, Punctuation and conventions/   # Parts of sentences, punctuation, spelling, etc.
├── Accessible and inclusive content/       # Accessibility and inclusion guidance
├── Writing and designing content/          # Plain language, voice, tone, editing
├── Structuring content/                    # Headings, lists, paragraphs, tables, links
├── Referencing and attribution/            # Legal material and citation guidance
├── Handbook/                               # Plain English writing handbook summaries
├── SiteMap.md                              # Navigation index for the rule library
├── Octavius_Rulebook_Column_Reference.docx # Column reference for rule authoring
└── Australian Government Style Manual_index.txt  # Full style manual index
```

When implementing a new rule, consult the relevant markdown files in this directory for the authoritative guidance text to use in `message` and `suggestion` fields.

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

## Rulebook creation pipeline (`src/`)

The `src/` directory holds the six-phase GitHub Actions pipeline that builds
the rulebook from the Australian Government Style Manual. The canonical
reference for this pipeline is `CLAUDE_Octavius Rulebook Creation Pipeline.md`.
Workflows live in `.github/workflows/phase*.yml`.

| File | Phase | Role |
|------|-------|------|
| `src/scrape.py` | 1 — Markdown Clone | Fetch sitemap, mirror pages to `content/` |
| `src/extract_rules.py` | 2 — Rule Extraction | LLM batch: page markdown → JSONL rules |
| `src/generate_code.py` | 3 — Rules as Code | LLM batch: rule → executable trigger code |
| `src/run_tests.py` | 4 — Test | Execute trigger code against test strings |
| `src/correct_rules.py` | 5 — Correct | LLM batch (gpt-4o): fix failing rules |
| `src/publish.py` | 6 — Publish | JSONL → `published/rulebook.parquet` |

### Phase 1 scraping notes

`src/scrape.py` is the Phase 1 entry point. A few conventions it must uphold
(learned from past failures):

- **Sitemap URL is a hard-coded default.** `src/scrape.py` defaults to
  `https://www.stylemanual.gov.au/sitemap.xml`. The `SITEMAP_URL` environment
  variable may override it for testing / mirrors, but it is no longer a
  GitHub Actions secret — the Style Manual is a public government site.
- **Sitemap fetch tries `requests` first, then Selenium.** The descriptive
  `OctaviusRulebookBot/1.0` User-Agent identifies us on non-browser
  requests. In April 2026 the Style Manual's WAF started silently dropping
  those requests (every fetch timed out after 30s), so `scrape.py` now falls
  back to Selenium for the sitemap and `robots.txt` whenever `requests`
  fails. Page fetches continue to use Selenium exclusively.
- **Sitemap payload may be XML *or* XSLT-rendered HTML.** The Style Manual's
  `/sitemap.xml` carries an XSLT stylesheet, so Selenium receives a
  fully-rendered `<table class="sitemap">` with one row per URL instead of
  raw XML. `parse_sitemap` sniffs the payload: XML goes through the
  namespaced `ElementTree` path; HTML goes through a BeautifulSoup table
  parser that treats the first `<td>` as the URL and the second as
  `lastmod`. Nested / paginated sitemaps are followed from either shape.
- **Fail loudly on zero URLs.** If parsing yields no URLs, Phase 1 aborts
  with `SystemExit` and logs a snippet of the response body, so a
  misconfigured `SITEMAP_URL` or unexpected response can be diagnosed from
  the Actions log rather than producing a no-op success.

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

**HTML/JS (`index.html`):** Vanilla ES2020. No build step. Keep all logic in the single file; extract constants to the top of the `<script>` block.
