# Octavius

A plain-language linter for Australian Public Service (APS) content. Paste or import a document, click **Analyse**, and Octavius highlights style violations inline with per-finding suggestions and a direct link to the source guidance in the Australian Government Style Manual.

**Stack:** Python + spaCy NLP backend served via FastAPI; React 18 + TypeScript + Tailwind CSS frontend served as a static page from the same process.

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
├── main.py                        # FastAPI entry point
├── routes/
│   ├── check.py                   # POST /check — runs the dispatcher
│   └── rules.py                   # GET /rules — rule metadata
├── logic/
│   ├── dispatcher.py              # Legacy dispatcher (runs every rule)
│   ├── indexed_dispatcher.py      # Indexed dispatcher (feature-gated, default)
│   ├── preprocess.py              # Segmentation, masking, counts
│   ├── features/
│   │   ├── extractor.py           # Feature extraction orchestrator
│   │   ├── vocabulary.py          # Frozen feature vocabulary + validator
│   │   ├── lexical.py             # HAS_DATE, HAS_URL, HAS_ABBREVIATION, …
│   │   ├── linguistic.py          # LING_PASSIVE_VOICE, LING_LONG_SENTENCE, …
│   │   ├── zones.py               # ZONE_HEADING, ZONE_LIST_BULLET, …
│   │   ├── patterns.py            # PATTERN_HEADING_TITLE_CASE, …
│   │   ├── relations.py           # REL_BULLET_AFTER_COLON, …
│   │   ├── aps.py                 # APS_LEGISLATION_REFERENCE, …
│   │   ├── document.py            # DOC_HAS_HEADINGS, DOC_HAS_LISTS, …
│   │   └── exemptions.py          # EXEMPT_URL, EXEMPT_CODE_SNIPPET, …
│   └── rulebook/
│       ├── loader.py              # Reads parquet, compiles rules
│       ├── adapters.py            # compile_regex / compile_lookup / compile_structural
│       ├── types.py               # Finding, CompiledRule, FeatureRequirements
│       └── spans.py               # find_term_spans helper
├── published/
│   └── rulebook.parquet           # Compiled, tested rulebook (source of truth)
├── rules_working_draft.jsonl      # Editable working copy of the rulebook
├── src/                           # Six-phase rulebook creation pipeline
├── frontend/
│   ├── src/
│   │   ├── OctaviusEditor.tsx     # Root component — editor, API call, decorations
│   │   ├── runtime/
│   │   │   ├── document.ts        # OctaviusDocument — AST wrapper + plain-text/zone projections
│   │   │   ├── serialisers.ts     # toPlainText, toZones, toCleanHTML, plainPosToPm
│   │   │   ├── mutations.ts       # applySentenceCaseHeading
│   │   │   └── schema.ts          # ProseMirror schema
│   │   ├── components/            # TextEditor, FindingsPanel, FindingCard, etc.
│   │   ├── hooks/
│   │   │   └── useHighlights.ts   # Text-segment slicing for highlight rendering
│   │   └── types.ts               # Shared TypeScript types (Finding, Zone, RuleMeta)
│   └── build/                     # Compiled bundle served by FastAPI
├── library_of_rules/              # Source material from the Australian Government Style Manual
├── tests/
│   └── test_engine.py
└── archive/                       # Previous implementations (reference only)
```

---

## Full system logic

### 1 — Rich-text editing (Tiptap)

The frontend uses **Tiptap** (a ProseMirror wrapper) as the editor. Tiptap gives Octavius a structured document AST rather than raw text, which is what makes structural zone detection possible in the browser before the request reaches the server.

When the editor content changes, the `OctaviusEditor` component wraps the live ProseMirror node in an `OctaviusDocument`:

```ts
const newOctDoc = OctaviusDocument.fromPMNode(ed.state.doc)
```

`OctaviusDocument` is a pure TypeScript class with no Tiptap or DOM dependencies. It lazily computes two projections of the AST:

| Projection | Description |
|---|---|
| `plainText` | Flat string: all leaf text nodes joined with `\n` separators between blocks |
| `zones` | Ordered list of `Zone` objects: `{kind, text, offset, length, ancestors, lintable}` |

**Zone kinds** match the ProseMirror node types: `heading`, `paragraph`, `list_bullet`, `list_numbered`, `table_cell`, `blockquote`, `code_fence`, `inline_code`, `footnote`, `reference_list`. `code_fence` and `inline_code` zones are marked `lintable: false` and are never sent to the rule engine.

The `offset` of each zone is its character position inside `plainText`, so `plainText.slice(zone.offset, zone.offset + zone.length) === zone.text` is an invariant.

### 2 — Sending the document to the server

After a 400 ms debounce, `runLint` calls `POST /check` with:

```json
{
  "plain_text": "...",
  "zones": [
    { "kind": "heading", "text": "...", "offset": 0, "length": 12, "ancestors": [], "lintable": true },
    { "kind": "paragraph", "text": "...", "offset": 13, "length": 220, "ancestors": [], "lintable": true }
  ]
}
```

The server returns findings as a flat JSON array:

```json
[
  {
    "rule_id": "writing-plain-english--avoid-jargon-001",
    "ui_flag": "Jargon detected",
    "rule_summary": "...",
    "start_char": 27,
    "end_char": 35,
    "severity": "warning",
    "mutation_class": "safe_replace",
    "document_level": false
  }
]
```

`start_char` and `end_char` are offsets into `plain_text`. After the response, the component maps each finding's character span back to a ProseMirror position using `OctaviusDocument.plainPosToPm()`, then dispatches a ProseMirror transaction that attaches inline `Decoration` nodes to the editor view, rendering the highlights without re-parsing the document.

### 3 — Preprocessing (`logic/preprocess.py`)

When the frontend supplies `zones`, `routes/check.py` calls `from_zones(text, zones)` to build a `PreprocessedDoc` directly from the browser's structural analysis — bypassing the fallback markdown-it-py segmenter that is used when plain text arrives without zone data.

Either path produces a `PreprocessedDoc` with:

| Field | Description |
|---|---|
| `segments` | List of `Segment(kind, text, offset, lintable, ancestors)` |
| `masked` | Copy of the original text where URLs, code snippets, filepaths, env vars, product names, identifiers, mentions, and quoted content are replaced with the private-use sentinel `` |
| `mask_map` | `(start, end, original, exemption_kind)` records — one per masked region |
| `sentence_count` | spaCy sentence count (regex fallback if spaCy unavailable) |
| `has_structure` | `True` if any heading, list, or code fence is present |
| `language` | `"en"` when ≥80% of letter characters are ASCII; `"und"` otherwise |
| `spacy_doc` | Cached spaCy `Doc` built from paragraph text |
| `counts` | Lightweight regex counts (`sentence`, `cardinal`, `acronym`, …) |

The masking step uses priority-ordered regex passes. Each character can belong to at most one `mask_map` entry. Masked regions are never highlighted by rules that use the masked text.

### 4 — Feature identification (coarse filter)

Before any rule code runs, the indexed dispatcher extracts a rich set of **boolean features** from each segment. These features act as a coarse filter: only rules whose declared `required_features` gate is satisfied by the segment's features are even attempted.

Feature extraction (`logic/features/extractor.py`) runs six sub-extractors in order:

| Sub-extractor | Examples |
|---|---|
| **zones** | `ZONE_HEADING`, `ZONE_LIST_BULLET`, `ANCESTOR_BLOCKQUOTE` |
| **lexical** | `HAS_DATE`, `HAS_URL`, `HAS_EM_DASH`, `HAS_DOUBLE_SPACE` |
| **linguistic** (spaCy) | `LING_PASSIVE_VOICE`, `LING_MODAL_VERB`, `LING_LONG_SENTENCE` |
| **patterns** | `PATTERN_HEADING_TITLE_CASE`, `PATTERN_BULLET_ENDS_WITH_PERIOD` |
| **relations** | `REL_BULLET_AFTER_COLON`, `REL_ACRONYM_DEFINED_ON_FIRST_USE` |
| **APS / domain** | `APS_LEGISLATION_REFERENCE`, `APS_MINISTERIAL_TITLE` |
| **exemptions** | `EXEMPT_URL`, `EXEMPT_CODE_SNIPPET`, `EXEMPT_QUOTED_CONTENT` |
| **document** | `DOC_HAS_HEADINGS`, `DOC_HAS_LISTS`, `DOC_LANGUAGE_EN` |

Document-level features (e.g. `DOC_HAS_HEADINGS`) are merged into every segment's feature set before candidate selection, so a rule that requires both `ZONE_PARAGRAPH` and `DOC_HAS_HEADINGS` fires only on paragraphs inside a headed document.

All feature names are validated against `logic/features/vocabulary.py`'s frozen `FEATURE_VOCABULARY`. Numeric thresholds are forbidden in feature names — they belong in extractor parameters.

### 5 — Inverted-index dispatcher (`logic/indexed_dispatcher.py`)

The indexed dispatcher is activated by setting `OCTAVIUS_DISPATCHER=indexed`. The legacy dispatcher (`logic/dispatcher.py`) runs every rule against every segment without feature gating.

**At boot**, the indexed dispatcher builds a three-part inverted index from each rule's `required_features` gate:

```
all_of:  ["ZONE_HEADING", "LING_TITLE_CASE_SEQUENCE"]  # ALL must be present
any_of:  ["HAS_DATE", "APS_DATE_LONGFORM"]              # AT LEAST ONE must be present
none_of: ["EXEMPT_CODE_SNIPPET"]                        # NONE may be present
```

Rules with `required_features = null` are *unconstrained* and always fire.

**Per segment**, `_compute_candidates(features)` performs the filter in O(rules) time:

```
candidates = set(UNCONSTRAINED_RULES)
for each constrained rule:
    if all_of not satisfied → skip
    if any_of not satisfied → skip
    if none_of violated    → skip
    candidates.add(rule_id)
```

Only candidate rules execute their `check(text)` function against the segment text. Results are cached per `(segment_text, features, candidates)` key via `SentenceCache`, so identical segments in the same document are never processed twice.

**Post-firing logic** runs after all segments:

1. **Firing budget** — each rule fires at most 5 spanned findings per document; overflow collapses into one document-level summary finding.
2. **Span deduplication** — exact `(start, end, rule_id)` triples are collapsed to one.
3. **Span grouping** — multiple rules firing on the same `(start, end)` span are merged into one finding with `grouped_rules` populated; `mutation_class` is the most conservative of the group.
4. **Document-level gating** — `(start=0, end=0)` findings are dropped when `not has_structure or sentence_count < 3` (short or unstructured documents are unlikely to warrant document-scope advice). Budget-overflow summaries bypass this gate.

### 6 — Rule execution (adapters)

`logic/rulebook/adapters.py` exposes three adapters, chosen by the rule's `taxonomy` field:

| Adapter | How it works |
|---|---|
| `compile_regex` | `trigger_code` is a bare regex pattern string; findings come from `re.finditer()` |
| `compile_lookup` | `trigger_code` defines `check_rule(text, lookup_list) → list[str]`; matched terms are located with `find_term_spans()` |
| `compile_structural` | `trigger_code` defines `check_rule(text) → list[str]`; return values locate spans |

`lookup` and `structural` trigger code is compiled once at startup via `compile()` + `exec()` in an isolated namespace. The rules are trusted (they passed Phase 4 testing) but run in a controlled globals dict without access to the host process.

### Complete data flow

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
   Candidate rules (feature-gated subset)
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
   ProseMirror DecorationSet → inline highlights
        │
        ▼
   FindingsPanel — per-finding cards, apply/acknowledge actions
```

### Applying fixes

Each finding carries a `mutation_class` that controls what the frontend offers the user:

| `mutation_class` | Frontend action |
|---|---|
| `safe_replace` | "Apply" button — replaces the spanned text with `finding.suggestion` automatically |
| `requires_rewrite` | "Apply" button — opens an editable field for the user to supply their own replacement |
| `human_review` | "Acknowledge" button only — no text mutation |
| `null` | Generic "Acknowledge" button |

Applying a fix calls `OctaviusDocument.applyFinding()`, which constructs a ProseMirror transaction, replaces the target text, and immediately re-triggers linting.

---

## Rulebook — adding, removing, and modifying rules

Rules live in `rules_working_draft.jsonl` (editable) and are published to `published/rulebook.parquet` (the file the app loads). The two files share the same column schema (see [Rulebook schema](#rulebook-schema)).

### Automatic: the six-phase pipeline

The `src/` directory contains a six-phase GitHub Actions pipeline that builds the rulebook from the Australian Government Style Manual:

| Phase | File | Role |
|---|---|---|
| 1 — Markdown Clone | `src/scrape.py` | Fetch sitemap, mirror Style Manual pages to `content/` |
| 2 — Rule Extraction | `src/extract_rules.py` | LLM batch: page markdown → JSONL rows |
| 3 — Rules as Code | `src/generate_code.py` | LLM batch: rule row → `trigger_code`, `ui_flag`, test strings |
| 3.5 — Feature Authoring | `src/extract_features.py` | LLM batch: rule row → `required_features`, `mutation_class` |
| 4 — Test | `src/run_tests.py` | Execute each rule's trigger code against `test_fire` / `test_no_fire` strings |
| 5 — Correct | `src/correct_rules.py` | LLM batch: fix failing rules; set `test_result = "pass"` |
| 6 — Publish | `src/publish.py` | Merge passing rows into `published/rulebook.parquet` |

Workflows live in `.github/workflows/phase*.yml`. Running the full pipeline from scratch re-scrapes the Style Manual, re-extracts rules, and re-publishes the parquet. The canonical design reference is `CLAUDE_Octavius Rulebook Creation Pipeline.md`.

### Manual: editing `rules_working_draft.jsonl` directly

For quick iteration without running the LLM phases, edit `rules_working_draft.jsonl` directly.

#### Add a rule

Append a new JSON line with all required fields. Minimum viable row:

```json
{
  "rule_id": "my-topic--my-rule-001",
  "source_url": "https://www.stylemanual.gov.au/...",
  "source_file": "content/my-topic/my-rule.md",
  "rule_summary": "One-sentence statement of the rule.",
  "rule_detail": "1–3 sentences with rationale.",
  "taxonomy": "regex",
  "discretionary_flag": false,
  "extracted_at": "2026-05-07T00:00:00Z",
  "method": "regex",
  "requires": [],
  "method_notes": "",
  "trigger_code": "\\bfinalise\\b",
  "ui_flag": "Use 'finalise' not 'finalize'",
  "test_fire": ["We will finalize the document."],
  "test_no_fire": ["We will finalise the document."],
  "lookup_list": [],
  "code_generated_at": "2026-05-07T00:00:00Z",
  "test_result": "pass",
  "test_run_at": "2026-05-07T00:00:00Z",
  "error_log": null,
  "correction_model": null,
  "required_features": null,
  "mutation_class": "safe_replace"
}
```

**Taxonomy and trigger code rules:**

- `regex`: `trigger_code` is a bare regex pattern string (compiled with `re.IGNORECASE`).
- `lookup`: `trigger_code` defines `def check_rule(text, lookup_list) -> list[str]`. Populate `lookup_list` with the terms to check.
- `structural`: `trigger_code` defines `def check_rule(text) -> list[str]`.
- `semantic`, `discretionary`, `multi-modal`, `unassigned`: set `trigger_code` to `null`; these rules never fire automatically.

**`required_features` gate (optional but recommended for performance):**

```json
"required_features": {
  "all_of": ["ZONE_PARAGRAPH"],
  "any_of": [],
  "none_of": ["EXEMPT_CODE_SNIPPET", "EXEMPT_QUOTED_CONTENT"]
}
```

Setting this to `null` causes the rule to run on every segment. Use feature gates to avoid false positives and reduce unnecessary rule executions. Feature names must come from the vocabulary in `logic/features/vocabulary.py`.

Then test and publish:

```bash
python src/run_tests.py      # sets test_result for each row
python src/publish.py        # writes published/rulebook.parquet
```

Restart the app to pick up the new rule.

#### Remove a rule

**Soft removal (recommended):** Change `test_result` to `"skip"` or `"frozen"` in `rules_working_draft.jsonl`, then re-publish. The loader only imports rows with `test_result == "pass"`.

**Hard removal:** Delete the row from `rules_working_draft.jsonl` and re-publish.

Either way, run:

```bash
python src/publish.py
```

Then restart the app.

#### Modify a rule

Edit the relevant fields in the matching row of `rules_working_draft.jsonl`. Common edits:

- Change `trigger_code` (regex pattern or Python function)
- Change `ui_flag` or `rule_summary` (user-facing text)
- Tighten or relax `required_features`
- Change `mutation_class` (controls which fix button the frontend shows)

After editing, re-run tests and republish:

```bash
python src/run_tests.py
python src/publish.py
```

Restart the app.

#### Freeze a rule

Set `test_result` to `"frozen"` to exclude a rule from the loader without deleting it. Frozen rules are preserved in the working draft but never loaded or published.

---

## Rulebook schema

`rules_working_draft.jsonl` and `published/rulebook.parquet` share the same column schema.

| Column | Type | Set by | Description |
|---|---|---|---|
| `rule_id` | string | Phase 2 | Unique stable identifier, e.g. `about-style-manual--changelog-001` |
| `source_url` | string | Phase 2 | Base URL of the Style Manual page the rule came from |
| `source_file` | string | Phase 2 | Relative path to the mirrored markdown file in `content/` |
| `rule_summary` | string | Phase 2 | One-sentence plain-English statement of the rule |
| `rule_detail` | string | Phase 2 | 1–3 sentence expansion with rationale |
| `taxonomy` | string | Phase 2 | Detection category: `regex`, `spacy`, `structural`, `lookup`, `semantic`, `contextual`, `discretionary`, `multi-modal`, or `unassigned` |
| `discretionary_flag` | boolean | Phase 2 | `true` when the source uses permissive language ("may", "consider", "optional") — sets severity to `info` instead of `warning` |
| `extracted_at` | string | Phase 2 | ISO 8601 timestamp of extraction |
| `method` | string | Phase 3 | Concrete detection approach |
| `requires` | list[string] | Phase 3 | Python packages or spaCy components the trigger code depends on |
| `method_notes` | string | Phase 3 | Implementation notes |
| `trigger_code` | string\|null | Phase 3 | Executable Python snippet or regex pattern; `null` for non-automatable taxonomies |
| `ui_flag` | string | Phase 3 | Short user-facing message shown in the findings panel |
| `test_fire` | list[string] | Phase 3 | Example strings where the rule **should** trigger |
| `test_no_fire` | list[string] | Phase 3 | Example strings where the rule **should not** trigger |
| `lookup_list` | list[string] | Phase 3 | Term list for `lookup`-taxonomy rules |
| `code_generated_at` | string | Phase 3 | ISO 8601 timestamp of code generation |
| `test_result` | string | Phase 4 | Last test outcome: `pass`, `fail`, `skip`, or `frozen` |
| `test_run_at` | string | Phase 4 | ISO 8601 timestamp of last test run |
| `error_log` | string\|null | Phase 4 | Error output captured during testing; `null` on success |
| `correction_model` | string\|null | Phase 5 | Model identifier used when Phase 5 rewrote trigger code; `null` if no correction needed |
| `required_features` | object\|null | Phase 3.5 | Feature gate: `{"all_of": [...], "any_of": [...], "none_of": [...]}`. `null` → always fires |
| `mutation_class` | string\|null | Phase 3.5 | Fix behaviour: `safe_replace`, `requires_rewrite`, or `human_review`. `null` → "Acknowledge" only |

> **Parquet storage note:** `requires`, `test_fire`, `test_no_fire`, and `lookup_list` are stored as `list<string>` Arrow arrays. `required_features` is split by `src/publish.py` into three `list<string>` columns (`required_features_all_of`, `_any_of`, `_none_of`) and reconstructed by `logic/rulebook/loader.py` at load time.

---

## Dispatcher modes

| Mode | How to activate | Behaviour |
|---|---|---|
| `legacy` | Default (no env var) | Runs every passing rule against the full document text on every request |
| `indexed` | `OCTAVIUS_DISPATCHER=indexed` | Feature-gated: only rules whose `required_features` gate is satisfied by the segment's features execute; results are segment-cached |

The indexed dispatcher is the preferred mode for production. The legacy dispatcher is useful for debugging (no feature gating means nothing is silently skipped).

---

## Phase 1 scraping notes

`src/scrape.py` mirrors the Australian Government Style Manual to `content/`:

- **Requests → Selenium fallback.** The `OctaviusRulebookBot/1.0` User-Agent is tried first via `requests`. Since April 2026 the Style Manual's WAF silently drops bot requests, so `scrape.py` falls back to Selenium for both the sitemap and `robots.txt` when `requests` times out. Page fetches always use Selenium.
- **XML or XSLT-rendered HTML.** The `/sitemap.xml` endpoint may return raw XML or a fully-rendered HTML table (the page carries an XSLT stylesheet). `parse_sitemap` sniffs the response and takes the appropriate path; nested sitemaps are followed recursively in either case.
- **Fail loudly on zero URLs.** If parsing yields no URLs, Phase 1 aborts with `SystemExit` and logs a snippet of the response body so the problem is immediately diagnosable from the Actions log.
- **`SITEMAP_URL` override.** The sitemap URL defaults to `https://www.stylemanual.gov.au/sitemap.xml`. Set the `SITEMAP_URL` repository variable (not a secret) to override for testing against a mirror.

---

## Contributing

Run `pytest tests/ -v` before opening a pull request. The rulebook is generated by the six-phase pipeline in `src/`; see `CLAUDE_Octavius Rulebook Creation Pipeline.md` for the full design.
