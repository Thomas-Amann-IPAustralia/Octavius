# Octavius

A plain-language linter for Australian Public Service (APS) content, built with FastAPI and spaCy.

Paste a block of text, click **Run audit**, and Octavius highlights style violations inline and lists each finding with a suggested fix.

> **Architecture:** Python + spaCy NLP backend served via FastAPI, with a React 18 + TypeScript + Tailwind CSS frontend served as a static page from the same app. Rule content is sourced from the Australian Government Style Manual, catalogued in `library_of_rules/`.

---

## Getting started

**Prerequisites:** Python 3.11+

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd Octavius

# 2. Install dependencies (includes the spaCy model)
pip install -r requirements.txt

# 3. Start the app
uvicorn main:app --reload
```

The app opens at `http://localhost:8000`.

---

## Running tests

```bash
pytest tests/ -v
```

---

## Project structure

```
Octavius/
├── main.py                   # FastAPI entry point — wires routers, serves index.html
├── routes/                   # FastAPI routers (POST /check, GET /rules, ...)
├── requirements.txt          # Python dependencies
├── logic/
│   ├── dispatcher.py         # run_rules() — loads compiled rulebook, runs every rule
│   └── rulebook/             # parquet loader + per-taxonomy adapters
├── frontend/
│   ├── src/
│   │   ├── OctaviusEditor.tsx        # Root React component (state, layout)
│   │   ├── components/               # TextEditor, FindingsPanel, FindingCard, etc.
│   │   ├── hooks/useHighlights.ts    # Text segmentation for inline highlights
│   │   └── types.ts                  # Shared TypeScript types
│   └── build/                        # Compiled bundle served by FastAPI
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

The rulebook is built by the `src/` pipeline (see "Rulebook creation
pipeline" below) and published as `published/rulebook.parquet`. At app
boot, `logic/dispatcher.py` loads the parquet, filters to rows with
`test_result == "pass"`, and compiles each rule into a uniform
`CompiledRule` via the per-taxonomy adapters in `logic/rulebook/`.

POST `/check` calls `dispatcher.run_rules(text, ...)`, which executes
every enabled rule against the text and returns sorted findings.

---

## Architecture

```
User input (frontend text area)
        │
        ▼
   POST /check  ──►  logic.dispatcher.run_rules(text, ...)
                              │
                              ▼
                   compiled rules (loaded once at boot
                   from published/rulebook.parquet)
                              │
                              ▼
            Findings (start_char, end_char, ui_flag, …)
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

Contributions are welcome. The rulebook is generated by the six-phase
pipeline in `src/` and published as `published/rulebook.parquet`; see
`CLAUDE_Octavius Rulebook Creation Pipeline.md` for the full flow.

Please run `pytest tests/ -v` before opening a pull request.
