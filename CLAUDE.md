# CLAUDE.md

## Project overview

Octavius is a plain-language linter for Australian Public Service (APS) content. It analyzes text for style violations and highlights them inline with suggestions and detailed findings.

The stack is:
- **Backend:** Python + spaCy NLP, served via FastAPI (`main.py`, `routes/`)
- **Frontend:** React 18 + TypeScript + Tailwind CSS, built to `frontend/build/` and served as a static page from FastAPI

Rules are sourced from the Australian Government Style Manual via the
six-phase pipeline in `src/`, published as `published/rulebook.parquet`,
and loaded at boot by `logic/dispatcher.py`.

---

## Commands

### Run the app
```bash
uvicorn main:app --reload
# Opens at http://localhost:8000
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
        React component (inline highlights + findings panel)
```

The React frontend lives in `frontend/`, builds to `frontend/build/`, and
is served as a static page by FastAPI alongside the JSON `/check` route.

---

## Key files

| File | Role |
|------|------|
| `main.py` | FastAPI entry point — wires routers, serves `index.html` |
| `routes/check.py` | POST `/check` — runs the dispatcher and returns findings |
| `routes/rules.py` | GET `/rules` and related rule-metadata endpoints |
| `logic/dispatcher.py` | Loads compiled rules at boot; `run_rules()` executes them |
| `logic/rulebook/loader.py` | Reads `published/rulebook.parquet` and compiles each row |
| `logic/rulebook/adapters.py` | Per-taxonomy adapters (regex / lookup / structural) |
| `logic/rulebook/types.py` | `Finding`, `CompiledRule`, `FeatureRequirements` TypedDicts |
| `logic/features/vocabulary.py` | Inverted-index feature vocabulary + validator (Phase 0) |
| `tests/` | Pytest unit and integration tests |
| `frontend/src/OctaviusEditor.tsx` | Root React component |
| `frontend/src/components/` | TextEditor, FindingsPanel, FindingCard, etc. |
| `frontend/src/hooks/useHighlights.ts` | Slices text into plain/highlighted segments |
| `frontend/src/types.ts` | Shared TypeScript types (Finding, Rule) |
| `library_of_rules/` | Reference rule content from the Australian Government Style Manual |
| `library_of_rules/SiteMap.md` | Navigation index for the rule library |
| `library_of_rules/Octavius_Rulebook_Column_Reference.docx` | Column reference for rule authoring |
| `docs/REFACTOR_LOG.md` | Decision log for the inverted-index refactor |

---

## Rule library (`library_of_rules/`)

The `library_of_rules/` directory contains reference content sourced from the Australian Government Style Manual. It is organised by topic and provides the authoritative source material for rules in the published rulebook (`published/rulebook.parquet`).

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

Rules are no longer hand-written in Python. They are produced by the
six-phase pipeline in `src/`: a Style Manual page is mirrored to markdown,
extracted into a JSONL row, given executable trigger code, tested,
corrected, and finally published as a row in
`published/rulebook.parquet`. The dispatcher loads the parquet at boot
and compiles every passing row via the per-taxonomy adapters in
`logic/rulebook/adapters.py`.

To iterate locally, edit `rules_working_draft.jsonl` and re-run the
relevant phases (`src/run_tests.py`, `src/correct_rules.py`,
`src/publish.py`); see `CLAUDE_Octavius Rulebook Creation Pipeline.md`
for the full flow.

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
| `src/extract_features.py` | 3.5 — Feature Authoring | LLM batch: rule → `required_features` + `mutation_class` |
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
| `required_features` | object\|null | Phase 3.5 | Feature gate: `{"all_of": [...], "any_of": [...], "none_of": [...]}`. `null` → dispatcher always retrieves the rule. In Parquet, stored as three separate `list<string>` columns: `required_features_all_of`, `required_features_any_of`, `required_features_none_of`. |
| `mutation_class` | string\|null | Phase 3.5 | How the rule's fix should be applied: `safe_replace`, `requires_rewrite`, or `human_review`. `null` → frontend shows generic "Acknowledge" button. |

> **Parquet-only note:** `requires`, `test_fire`, `test_no_fire`, and
> `lookup_list` are stored as `list<string>` Arrow arrays in the Parquet file.
> The JSONL represents them as JSON arrays (or `null`); `src/publish.py`
> normalises `null` → `[]` and bare strings → `[value]` before writing.
>
> `required_features` is stored in JSONL as a nested object (or `null`) and
> split by `src/publish.py` into three separate `list<string>` Parquet columns
> (`required_features_all_of`, `_any_of`, `_none_of`). `logic/rulebook/loader.py`
> reconstructs the `FeatureRequirements` dict at load time. See
> `docs/REFACTOR_LOG.md` Phase 3.5 for the rationale.

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
