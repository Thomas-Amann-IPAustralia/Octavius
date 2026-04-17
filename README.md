# Octavius

A plain-language linter for Australian Public Service (APS) content, built with Streamlit and spaCy.

Paste a block of text, click **Run audit**, and Octavius highlights style violations inline and lists each finding with a suggested fix.

> **Architecture:** Python + spaCy NLP backend, React 18 + TypeScript + Tailwind CSS frontend (embedded as a Streamlit custom component). Rule content is sourced from the Australian Government Style Manual, catalogued in `library_of_rules/`.

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
├── app.py                    # Streamlit UI — page layout, session state, result rendering
├── requirements.txt          # Python dependencies
├── logic/
│   ├── engine.py             # lint_text() — runs rules against a spaCy Doc
│   └── rules.py              # RULES list + individual rule check functions
├── frontend/
│   ├── src/
│   │   ├── OctaviusEditor.tsx        # Root React component (state, layout)
│   │   ├── components/               # TextEditor, FindingsPanel, FindingCard, etc.
│   │   ├── hooks/useHighlights.ts    # Text segmentation for inline highlights
│   │   └── types.ts                  # Shared TypeScript types
│   └── build/                        # Compiled component (loaded by Streamlit)
├── library_of_rules/         # Reference rule content from the Australian Government Style Manual
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

## Rulebook creation pipeline

The `src/` directory contains the six-phase GitHub Actions pipeline that builds
the rulebook from the Australian Government Style Manual. The full design lives
in `CLAUDE_Octavius Rulebook Creation Pipeline.md`; the scraping step in
particular is worth knowing about:

**Phase 1 — `src/scrape.py`** mirrors the Style Manual to markdown in
`content/`. It:

- Tries the sitemap with `requests` + the `OctaviusRulebookBot/1.0`
  User-Agent first, and falls back to Selenium if the WAF drops the
  request (as `stylemanual.gov.au` started doing in April 2026). Page
  fetches always use Selenium, where a browser-like User-Agent and JS
  rendering are needed.
- Accepts either raw XML or the XSLT-rendered HTML table that browsers
  receive for the Style Manual's `/sitemap.xml`. Both shapes flow through
  the same `parse_sitemap` entry point; nested / paginated sitemaps are
  followed recursively in either case.
- Aborts with a clear error (and logs a snippet of the response) if
  parsing yields zero URLs, so a misconfigured `SITEMAP_URL` or unexpected
  response is surfaced immediately rather than silently doing nothing.

The sitemap URL defaults to `https://www.stylemanual.gov.au/sitemap.xml`
and can be overridden via the `SITEMAP_URL` environment variable (set as a
repository variable, not a secret) for testing against a mirror. The
workflow lives in `.github/workflows/phase1_scrape.yml`.

---

## Rulebook schema (JSONL and Parquet)

The working draft (`rules_working_draft.jsonl`) and the published artefact
(`published/rulebook.parquet`) share the same column schema. The JSONL is the
mutable, line-delimited format used throughout Phases 2–5; Phase 6
(`src/publish.py`) converts it to Parquet (Snappy-compressed) with proper Arrow
types for list columns.

| Column | Type | Set by | Description |
|--------|------|--------|-------------|
| `rule_id` | string | Phase 2 | Unique stable identifier, e.g. `about-style-manual--changelog-001` |
| `source_url` | string | Phase 2 | Base URL of the Style Manual page the rule came from |
| `source_file` | string | Phase 2 | Relative path to the mirrored markdown file in `content/` |
| `rule_summary` | string | Phase 2 | One-sentence plain-English statement of the rule |
| `rule_detail` | string | Phase 2 | 1–3 sentence expansion with rationale |
| `taxonomy` | string | Phase 2 | Detection category: `regex`, `spacy`, `structural`, `lookup`, `semantic`, `contextual`, `discretionary`, `multi-modal`, or `unassigned` |
| `discretionary_flag` | boolean | Phase 2 | `true` when the source uses permissive language ("may", "consider", "optional") |
| `extracted_at` | string | Phase 2 | ISO 8601 timestamp of extraction |
| `method` | string | Phase 3 | Concrete detection approach (`regex`, `spacy`, `lookup`, `structural`, `manual`, …) |
| `requires` | list[string] | Phase 3 | Python packages or spaCy components the trigger code depends on |
| `method_notes` | string | Phase 3 | Implementation notes for the detection method |
| `trigger_code` | string\|null | Phase 3 | Executable Python snippet; `null` for `semantic`, `discretionary`, and `multi-modal` rules that cannot be auto-detected |
| `ui_flag` | string | Phase 3 | Short user-facing message shown in the findings panel |
| `test_fire` | list[string] | Phase 3 | Example strings where the rule **should** trigger |
| `test_no_fire` | list[string] | Phase 3 | Example strings where the rule **should not** trigger |
| `lookup_list` | list[string] | Phase 3 | Reference word/phrase list for `lookup`-taxonomy rules |
| `code_generated_at` | string | Phase 3 | ISO 8601 timestamp of code generation |
| `test_result` | string | Phase 4 | Last test outcome: `pass`, `fail`, `skip`, or `frozen` |
| `test_run_at` | string | Phase 4 | ISO 8601 timestamp of last test run |
| `error_log` | string\|null | Phase 4 | Error output captured during testing; `null` on success |
| `correction_model` | string\|null | Phase 5 | Model identifier used when Phase 5 rewrote the trigger code; `null` if no correction was needed |

> **Parquet-only note:** `requires`, `test_fire`, `test_no_fire`, and
> `lookup_list` are stored as `list<string>` Arrow arrays in the Parquet file.
> The JSONL represents them as JSON arrays (or `null`); `src/publish.py`
> normalises `null` → `[]` and bare strings → `[value]` before writing.

---

## Contributing

Contributions are welcome. The most impactful place to start is adding new rules to `logic/rules.py` — see the section above for how rules are structured.

Please run `pytest tests/ -v` before opening a pull request.
