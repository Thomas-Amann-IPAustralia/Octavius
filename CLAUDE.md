# CLAUDE.md

## Project overview

Octavius is a plain-language linter for Australian Public Service (APS) content. It analyzes text for style violations and highlights them inline with suggestions and detailed findings.

The stack is:
- **Backend:** Python + spaCy NLP, served via FastAPI (`main.py`, `routes/`)
- **Frontend:** React 18 + TypeScript + Tailwind CSS, built to `frontend/build/` and served as a static page from FastAPI

Rules are sourced from the Australian Government Style Manual via the six-phase pipeline in `src/`, published as `published/rulebook.parquet`, and loaded at boot by `logic/dispatcher.py` or `logic/indexed_dispatcher.py`.

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
User input (Tiptap editor)
        │
        │  OctaviusDocument.fromPMNode()
        ▼
   plainText + zones
        │
        │  POST /check  (debounced 400ms)
        ▼
   routes/check.py
        │
        │  from_zones() — build PreprocessedDoc from Tiptap zone data
        │                 (skips markdown segmentation for rich-text input)
        ▼
   logic.preprocess.PreprocessedDoc
   ├── segments (kind, text, offset, lintable, ancestors)
   ├── masked text + mask_map (EXEMPT_URL, EXEMPT_CODE_SNIPPET, …)
   ├── sentence_count, has_structure, language
   └── spacy_doc (cached)
        │
        │  logic.features.extractor.extract()
        ▼
   FeatureSet
   ├── per_segment: [frozenset[str], …]   # ZONE_*, LING_*, HAS_*, …
   └── document:    frozenset[str]         # DOC_*, EXEMPT_* across full doc
        │
        │  _compute_candidates(seg_features | doc_features)
        ▼
   Candidate rules (feature-gated subset of all compiled rules)
        │
        │  rule["check"](segment_text)  — per candidate, per segment
        ▼
   Raw findings (segment-relative offsets)
        │
        │  Post-firing: budget → dedup → group → doc-level gate
        ▼
   Findings (start_char, end_char into plain_text)
        │
        │  OctaviusDocument.plainPosToPm()
        ▼
   ProseMirror DecorationSet → inline highlights + FindingsPanel
```

---

## Key files

| File | Role |
|---|---|
| `main.py` | FastAPI entry point — wires routers, serves `index.html` |
| `routes/check.py` | POST `/check` — preprocesses zones, selects dispatcher, returns findings |
| `routes/rules.py` | GET `/rules` and related rule-metadata endpoints |
| `logic/dispatcher.py` | Legacy dispatcher: loads compiled rules at boot; `run_rules()` executes every rule without feature gating |
| `logic/indexed_dispatcher.py` | Indexed dispatcher: feature-gated inverted-index runner; preferred for production |
| `logic/preprocess.py` | Segmentation (markdown-it or from zones), masking, counts, language detection |
| `logic/features/extractor.py` | Feature extraction orchestrator — calls all sub-extractors |
| `logic/features/vocabulary.py` | Frozen `FEATURE_VOCABULARY` frozenset + threshold-suffix validator |
| `logic/features/lexical.py` | HAS_DATE, HAS_URL, HAS_EM_DASH, HAS_ABBREVIATION, … |
| `logic/features/linguistic.py` | LING_PASSIVE_VOICE, LING_MODAL_VERB, LING_LONG_SENTENCE, … (spaCy) |
| `logic/features/zones.py` | ZONE_HEADING, ZONE_LIST_BULLET, ANCESTOR_BLOCKQUOTE, … |
| `logic/features/patterns.py` | PATTERN_HEADING_TITLE_CASE, PATTERN_BULLET_ENDS_WITH_PERIOD, … |
| `logic/features/relations.py` | REL_BULLET_AFTER_COLON, REL_ACRONYM_DEFINED_ON_FIRST_USE, … |
| `logic/features/aps.py` | APS_LEGISLATION_REFERENCE, APS_MINISTERIAL_TITLE, … |
| `logic/features/document.py` | DOC_HAS_HEADINGS, DOC_HAS_LISTS, DOC_HAS_CITATIONS, … |
| `logic/features/exemptions.py` | EXEMPT_URL, EXEMPT_CODE_SNIPPET, EXEMPT_QUOTED_CONTENT, … |
| `logic/rulebook/loader.py` | Reads `published/rulebook.parquet`, filters to `test_result == "pass"`, compiles each row |
| `logic/rulebook/adapters.py` | `compile_regex` / `compile_lookup` / `compile_structural` |
| `logic/rulebook/types.py` | `Finding`, `CompiledRule`, `FeatureRequirements` TypedDicts |
| `logic/sentence_cache.py` | LRU cache for per-segment rule results (keyed on segment text + features + candidates) |
| `tests/` | Pytest unit and integration tests |
| `frontend/src/OctaviusEditor.tsx` | Root React component — Tiptap editor, API call, decoration dispatch, finding actions |
| `frontend/src/runtime/document.ts` | `OctaviusDocument` — AST wrapper, `plainText`, `zones`, `plainPosToPm`, `applyFinding` |
| `frontend/src/runtime/serialisers.ts` | `toPlainText`, `toZones`, `toCleanHTML`, `plainPosToPm` |
| `frontend/src/runtime/mutations.ts` | `applySentenceCaseHeading` |
| `frontend/src/components/` | TextEditor, FindingsPanel, FindingCard, etc. |
| `frontend/src/hooks/useHighlights.ts` | Slices text into plain/highlighted segments |
| `frontend/src/types.ts` | Shared TypeScript types (Finding, Zone, RuleMeta) |
| `library_of_rules/` | Reference rule content from the Australian Government Style Manual |
| `library_of_rules/SiteMap.md` | Navigation index for the rule library |
| `library_of_rules/Octavius_Rulebook_Column_Reference.docx` | Column reference for rule authoring |
| `docs/REFACTOR_LOG.md` | Decision log for the inverted-index refactor |
| `published/rulebook.parquet` | Compiled, tested rulebook — the file the app loads at boot |
| `rules_working_draft.jsonl` | Editable working copy of the rulebook |

---

## How the system works end-to-end

### Tiptap and the OctaviusDocument

The frontend uses **Tiptap** (ProseMirror wrapper) as the editor. Every content change triggers:

```ts
const newOctDoc = OctaviusDocument.fromPMNode(ed.state.doc)
scheduleLint(newOctDoc)   // debounced 400 ms
```

`OctaviusDocument` lazily computes two projections of the ProseMirror AST:

- **`plainText`** — flat string: all leaf text nodes joined with `\n` separators between blocks
- **`zones`** — ordered list of `Zone` objects: `{kind, text, offset, length, ancestors, lintable}`

Zone `offset` is the character position of `zone.text[0]` inside `plainText`. The invariant `plainText.slice(zone.offset, zone.offset + zone.length) === zone.text` is enforced by the single-pass serialiser in `serialisers.ts`.

**Zone kinds:** `heading`, `paragraph`, `list_bullet`, `list_numbered`, `table_cell`, `blockquote`, `code_fence`, `inline_code`, `footnote`, `reference_list`. `code_fence` and `inline_code` are marked `lintable: false` and skipped by the dispatcher.

### POST /check and zone-based preprocessing

`runLint` sends `POST /check` with `plain_text` and the `zones` array. In `routes/check.py`, when zones are present the server calls `logic.preprocess.from_zones(text, zones)` to build a `PreprocessedDoc` directly from the Tiptap structural analysis — bypassing the fallback markdown-it-py segmenter.

The `PreprocessedDoc` contains:
- `segments`: list of `Segment(kind, text, offset, lintable, ancestors)` — one per zone
- `masked`: copy of original text with non-prose regions (URLs, code, filepaths, env vars, identifiers, product names, quoted content) replaced with the sentinel ``
- `mask_map`: `(start, end, original, exemption_kind)` records for every masked region
- `sentence_count`, `has_structure`, `language`, `spacy_doc`, `counts`

### Feature identification as coarse filter

Before any rule runs, `logic.features.extractor.extract(doc, nlp)` annotates every segment with boolean features. These features are the **coarse filter** that the indexed dispatcher uses to skip rules that cannot possibly match.

Sub-extractors (in order):

1. **zones** — segment structural kind + ancestors (`ZONE_HEADING`, `ANCESTOR_TABLE`, …)
2. **lexical** — token observations (`HAS_DATE`, `HAS_URL`, `HAS_DOUBLE_SPACE`, …)
3. **linguistic** — spaCy POS/dep-parse (`LING_PASSIVE_VOICE`, `LING_LONG_SENTENCE`, …); batched across all lintable segments with `nlp.pipe()` to amortise tok2vec cost
4. **patterns** — multi-token patterns (`PATTERN_HEADING_TITLE_CASE`, `PATTERN_BULLET_ENDS_WITH_PERIOD`, …)
5. **relations** — cross-segment observations (`REL_BULLET_AFTER_COLON`, …)
6. **APS / domain** — government-specific terms (`APS_LEGISLATION_REFERENCE`, `APS_MINISTERIAL_TITLE`, …)
7. **exemptions** — derived from `mask_map` (`EXEMPT_URL`, `EXEMPT_CODE_SNIPPET`, …)
8. **document** — document-scope booleans (`DOC_HAS_HEADINGS`, `DOC_HAS_LISTS`, …) merged into every segment

All feature names are validated against `FEATURE_VOCABULARY` in `logic/features/vocabulary.py`. Numeric thresholds are forbidden in feature names (guarded by regex); they belong in extractor parameters.

### Inverted-index dispatcher

Activated with `OCTAVIUS_DISPATCHER=indexed`. At boot, `_build_index()` constructs three inverted index dicts and a frozenset of unconstrained rule IDs from each rule's `required_features` gate.

Per segment, `_compute_candidates(features)` runs in O(rules) time:

```python
candidates = set(_UNCONSTRAINED)
for rule_id in _CONSTRAINED_IDS:
    all_of = _RULE_ALL_OF[rule_id]   # frozenset
    any_of = _RULE_ANY_OF[rule_id]
    none_of = _RULE_NONE_OF[rule_id]
    if all_of and not (all_of <= features): continue
    if any_of and not (any_of & features): continue
    if none_of and (none_of & features):   continue
    candidates.add(rule_id)
```

Only candidate rules execute. Results are cached in `SentenceCache` keyed on `(segment_text, features, candidates)`.

Post-firing: firing budget (max 5 spanned findings per rule) → span dedup → span grouping → document-level gating (suppressed for short/unstructured docs).

**Dispatcher selection:** `OCTAVIUS_DISPATCHER` env var — `"indexed"` or `"legacy"` (default). The legacy dispatcher runs every rule against the full text with no feature gating, useful for debugging.

---

## Rule library (`library_of_rules/`)

```
library_of_rules/
├── Grammar, Punctuation and conventions/
├── Accessible and inclusive content/
├── Writing and designing content/
├── Structuring content/
├── Referencing and attribution/
├── Handbook/
├── SiteMap.md
├── Octavius_Rulebook_Column_Reference.docx
└── Australian Government Style Manual_index.txt
```

When authoring a new rule, consult the relevant markdown files here for the authoritative guidance text to use in `rule_summary`, `rule_detail`, `ui_flag`, and `suggestion` fields.

---

## Adding, removing, and modifying rules

Rules exist in two files: `rules_working_draft.jsonl` (editable source of truth) and `published/rulebook.parquet` (the compiled file the app loads). The workflow is always: edit the JSONL → test → publish → restart the app.

### Automatic: pipeline phases

Run individual pipeline phases to add or refresh rules from the Style Manual:

```bash
python src/scrape.py          # Phase 1: mirror Style Manual pages to content/
python src/extract_rules.py   # Phase 2: LLM → JSONL rows
python src/generate_code.py   # Phase 3: LLM → trigger_code, test strings
python src/extract_features.py # Phase 3.5: LLM → required_features, mutation_class
python src/run_tests.py        # Phase 4: test every rule's trigger code
python src/correct_rules.py    # Phase 5: LLM → fix failing rules
python src/publish.py          # Phase 6: JSONL → parquet
```

GitHub Actions workflows in `.github/workflows/phase*.yml` run these automatically. See `CLAUDE_Octavius Rulebook Creation Pipeline.md` for the full design.

### Manual: edit `rules_working_draft.jsonl` directly

#### Add a rule

Append a new JSON line. Minimum viable regex rule:

```json
{
  "rule_id": "my-topic--my-rule-001",
  "source_url": "https://www.stylemanual.gov.au/...",
  "source_file": "content/my-topic/my-rule.md",
  "rule_summary": "One-sentence statement.",
  "rule_detail": "1–3 sentences with rationale.",
  "taxonomy": "regex",
  "discretionary_flag": false,
  "extracted_at": "2026-05-07T00:00:00Z",
  "method": "regex",
  "requires": [],
  "method_notes": "",
  "trigger_code": "\\bfinalize\\b",
  "ui_flag": "Use 'finalise' (Australian spelling)",
  "test_fire": ["We will finalize the plan."],
  "test_no_fire": ["We will finalise the plan."],
  "lookup_list": [],
  "code_generated_at": "2026-05-07T00:00:00Z",
  "test_result": "pass",
  "test_run_at": "2026-05-07T00:00:00Z",
  "error_log": null,
  "correction_model": null,
  "required_features": {"all_of": [], "any_of": [], "none_of": ["EXEMPT_CODE_SNIPPET"]},
  "mutation_class": "safe_replace"
}
```

**Taxonomy choices:**
- `regex` — `trigger_code` is a bare pattern string compiled with `re.IGNORECASE`
- `lookup` — `trigger_code` defines `def check_rule(text, lookup_list) -> list[str]`; populate `lookup_list` with the terms
- `structural` — `trigger_code` defines `def check_rule(text) -> list[str]`
- `semantic`, `discretionary`, `multi-modal`, `unassigned` — set `trigger_code` to `null`; never auto-detect

**`required_features` gate:** Use `null` to run on every segment. Prefer explicit gates to avoid false positives and unnecessary execution. Feature names must be in `logic/features/vocabulary.FEATURE_VOCABULARY`. Use `none_of` to exclude exempt regions (e.g., `EXEMPT_CODE_SNIPPET`, `EXEMPT_URL`). `EXEMPT_*` features must never appear in `all_of` or `any_of` (the dispatcher rejects and silently drops such rules).

Then:

```bash
python src/run_tests.py
python src/publish.py
# restart the app
```

#### Remove a rule

**Soft removal (preferred):** Set `test_result` to `"skip"` or `"frozen"` — the loader ignores everything that isn't `"pass"`.

**Hard removal:** Delete the row.

Either way, re-publish:

```bash
python src/publish.py
```

#### Modify a rule

Edit the fields you want to change (typically `trigger_code`, `ui_flag`, `required_features`, or `mutation_class`), then:

```bash
python src/run_tests.py
python src/publish.py
```

Verify with `pytest tests/ -v` that no existing tests regress.

#### Freeze a rule

Set `test_result` to `"frozen"` to preserve the row in the working draft but permanently exclude it from loading. Useful for rules that are correct but have too many false positives for the current rule engine.

---

## Rulebook creation pipeline (`src/`)

The `src/` directory holds the six-phase GitHub Actions pipeline. The canonical reference is `CLAUDE_Octavius Rulebook Creation Pipeline.md`.

| File | Phase | Role |
|---|---|---|
| `src/scrape.py` | 1 — Markdown Clone | Fetch sitemap, mirror pages to `content/` |
| `src/extract_rules.py` | 2 — Rule Extraction | LLM batch: page markdown → JSONL rules |
| `src/generate_code.py` | 3 — Rules as Code | LLM batch: rule → trigger code, test strings |
| `src/extract_features.py` | 3.5 — Feature Authoring | LLM batch: rule → `required_features` + `mutation_class` |
| `src/run_tests.py` | 4 — Test | Execute trigger code against `test_fire` / `test_no_fire` strings |
| `src/correct_rules.py` | 5 — Correct | LLM batch: fix failing rules |
| `src/publish.py` | 6 — Publish | JSONL → `published/rulebook.parquet` |

### Phase 1 scraping notes

- **Sitemap default.** `src/scrape.py` defaults to `https://www.stylemanual.gov.au/sitemap.xml`. Override with the `SITEMAP_URL` repository variable.
- **Requests → Selenium fallback.** Since April 2026 the Style Manual WAF drops bot requests, so `scrape.py` falls back to Selenium when `requests` times out. Page fetches always use Selenium.
- **XML or XSLT HTML.** `parse_sitemap` sniffs the response shape; both paths follow nested sitemaps recursively.
- **Fail loudly on zero URLs.** `SystemExit` + response snippet if no URLs are parsed.

---

## Rulebook schema (JSONL and Parquet)

| Column | Type | Set by | Description |
|---|---|---|---|
| `rule_id` | string | Phase 2 | Unique stable identifier |
| `source_url` | string | Phase 2 | Style Manual page URL |
| `source_file` | string | Phase 2 | Path to mirrored markdown in `content/` |
| `rule_summary` | string | Phase 2 | One-sentence rule statement |
| `rule_detail` | string | Phase 2 | 1–3 sentence expansion |
| `taxonomy` | string | Phase 2 | `regex`, `lookup`, `structural`, `semantic`, `contextual`, `discretionary`, `multi-modal`, or `unassigned` |
| `discretionary_flag` | boolean | Phase 2 | `true` → severity `info`; `false` → `warning` |
| `extracted_at` | string | Phase 2 | ISO 8601 |
| `method` | string | Phase 3 | Concrete detection approach |
| `requires` | list[string] | Phase 3 | Python packages or spaCy components needed |
| `method_notes` | string | Phase 3 | Implementation notes |
| `trigger_code` | string\|null | Phase 3 | Regex pattern or Python function; `null` for non-automatable taxonomies |
| `ui_flag` | string | Phase 3 | Short message shown in the findings panel |
| `test_fire` | list[string] | Phase 3 | Strings that **must** trigger the rule |
| `test_no_fire` | list[string] | Phase 3 | Strings that **must not** trigger the rule |
| `lookup_list` | list[string] | Phase 3 | Term list for `lookup`-taxonomy rules |
| `code_generated_at` | string | Phase 3 | ISO 8601 |
| `test_result` | string | Phase 4 | `pass`, `fail`, `skip`, or `frozen` — loader only imports `pass` |
| `test_run_at` | string | Phase 4 | ISO 8601 |
| `error_log` | string\|null | Phase 4 | Error output; `null` on success |
| `correction_model` | string\|null | Phase 5 | Model used by Phase 5; `null` if no correction needed |
| `required_features` | object\|null | Phase 3.5 | `{"all_of": [...], "any_of": [...], "none_of": [...]}`. `null` → unconstrained |
| `mutation_class` | string\|null | Phase 3.5 | `safe_replace`, `requires_rewrite`, or `human_review`. `null` → "Acknowledge" only |

> **Parquet note:** `requires`, `test_fire`, `test_no_fire`, and `lookup_list` are `list<string>` Arrow arrays. `required_features` is split into three separate `list<string>` columns (`required_features_all_of`, `_any_of`, `_none_of`) by `src/publish.py` and reconstructed by `logic/rulebook/loader.py`. See `docs/REFACTOR_LOG.md` Phase 3.5 for the rationale.

---

## Testing guidance

- Tests live in `tests/test_engine.py` and use pytest.
- Run `pytest tests/ -v` before opening a pull request.
- Test new rules by asserting that `lint_text` returns the expected findings for known inputs.
- The `archive/` directory contains previous implementations — do not modify it.

---

## Code style

**Python:** Use type hints (TypedDict, list, Optional). Follow existing module structure. No linter is configured; match the style of surrounding code.

**TypeScript:** Strict mode is enabled. Use the existing `Finding`, `Zone`, and `RuleMeta` types from `types.ts`. Style with Tailwind utility classes.
