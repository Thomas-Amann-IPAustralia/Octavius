Here's the full plan. It's long because each prompt needs to be self-contained, but the structure is: (1) overview, (2) cross-cutting decisions you fix once, (3) seven phase prompts (Phase 0–6) you paste one at a time, (4) risks. Skim section 1 + 2 first, then use sections 3 onward as reference.

---

# 1. Overview

```
Phase 0  Foundations             — schema, decision log, delete stale code        ½ day
Phase 1  Preprocessing layer     — markdown segmentation, masking, sentence cache  1 day
Phase 2  Feature extractor       — spaCy + regex + structural → feature set        1–2 days
Phase 3  Authoring batch         — LLM run to add `required_features` per rule     ½ day + batch wait
Phase 4  Indexed dispatcher      — inverted index, dedup, firing budget, env flag  1–2 days
Phase 5  Corpus + telemetry      — calibration corpus, precision scoring, report   1 day
Phase 6  Frontend + cutover      — React updates, default flip, legacy removal     1 day
```

Each phase = one Claude Code session = one branch + one PR into the long-lived integration branch.

# 2. Cross-cutting decisions (set once, reused everywhere)

**Integration branch:** `claude/inverted-index-refactor`. Every per-phase PR merges here. Final PR merges this into `main` after Phase 6.

**Per-phase branch naming:** `claude/iir-phase-{N}-{short-slug}` (e.g. `claude/iir-phase-1-preprocessing`).

**Decision log:** create `docs/REFACTOR_LOG.md` in Phase 0. Every phase appends a dated section with: what shipped, what was deferred, surprises, follow-ups. This is how context survives between Claude Code sessions.

**Migration flag:** `OCTAVIUS_DISPATCHER` env var, values `legacy | indexed`, default `legacy` until Phase 6 flips it. `routes/check.py` imports the chosen module at startup. Both dispatchers must satisfy the same `run_rules(text, ...) -> list[Finding]` signature.

**Feature vocabulary** (canonical, frozen at end of Phase 0). Stored as `logic/features/vocabulary.py`:

```
ZONE_*           (structural, from markdown tree)
  ZONE_HEADING, ZONE_PARAGRAPH, ZONE_LIST_BULLET, ZONE_LIST_NUMBERED,
  ZONE_TABLE, ZONE_BLOCKQUOTE, ZONE_CODE_FENCE, ZONE_INLINE_CODE,
  ZONE_FOOTNOTE, ZONE_REFERENCE_LIST

HAS_*            (lexical / token, from regex on segment text)
  HAS_CARDINAL, HAS_ORDINAL, HAS_PERCENT, HAS_CURRENCY, HAS_DATE, HAS_TIME,
  HAS_URL, HAS_EMAIL, HAS_ABBREVIATION, HAS_ACRONYM, HAS_ROMAN_NUMERAL,
  HAS_EM_DASH, HAS_EN_DASH, HAS_HYPHEN, HAS_COLON, HAS_SEMICOLON,
  HAS_STRAIGHT_QUOTE, HAS_CURLY_QUOTE, HAS_DOUBLE_SPACE, HAS_PARENTHESES

LING_*           (linguistic, from spaCy)
  LING_PASSIVE_VOICE, LING_MODAL_VERB, LING_FIRST_PERSON, LING_SECOND_PERSON,
  LING_IMPERATIVE, LING_PROPER_NOUN, LING_TITLE_CASE_SEQUENCE,
  LING_ALL_CAPS_TOKEN, LING_NEGATION, LING_LONG_SENTENCE_25P

PATTERN_*        (multi-token regex / structural)
  PATTERN_NUMERIC_RANGE, PATTERN_CITATION_PARENS, PATTERN_HEADING_TITLE_CASE,
  PATTERN_HEADING_SENTENCE_CASE, PATTERN_BULLET_PUNCTUATED,
  PATTERN_BULLET_FRAGMENT, PATTERN_REGNAL_NUMERAL_SHAPE,
  PATTERN_LEGAL_CITATION_SHAPE

APS_*            (domain-specific lookup)
  APS_LEGISLATION_REFERENCE, APS_DEPARTMENT_NAME, APS_MINISTERIAL_TITLE,
  APS_DATE_LONGFORM, APS_COMMONWEALTH_ENTITY

MASK_*           (negative; never required, only forbidden)
  MASK_URL, MASK_FILEPATH, MASK_BRANCHNAME, MASK_IDENTIFIER,
  MASK_ENV_VAR, MASK_PRODUCT_NAME, MASK_MENTION_OR_HASHTAG,
  MASK_CODE_SNIPPET

DOC_*            (document-scope; computed once per call)
  DOC_HAS_HEADINGS, DOC_HAS_LISTS, DOC_HAS_CITATIONS,
  DOC_SENTENCE_COUNT_GE_3, DOC_SENTENCE_COUNT_GE_10,
  DOC_LANGUAGE_EN
```

**Required-features schema (per rule):** new parquet column `required_features: dict[str, list[str]]` with three keys:
```python
{"all_of": ["LING_PASSIVE_VOICE"], "any_of": ["ZONE_PARAGRAPH"], "none_of": ["MASK_CODE_SNIPPET"]}
```
A rule retrieves iff:
- every feature in `all_of` is present, AND
- (`any_of` is empty OR at least one feature in it is present), AND
- no feature in `none_of` is present.

**Hard guardrails enforced in every prompt:**
- Don't modify trigger code in the parquet by hand. New column only.
- Don't break the legacy dispatcher until Phase 6.
- All new code uses `from __future__ import annotations`, type hints, no bare `except`, no swallowed errors.
- `pytest tests/ -v` must pass at every commit.
- No new dependencies without justification in commit message; Polars/DuckDB are explicitly **excluded** at this scale.

**Latency budget.** 700ms hard cap, 200ms target. Document each phase's measured cost in `REFACTOR_LOG.md` so we know where the budget is going.

---

# 3. Phase prompts

Each block is paste-ready. Start a fresh Claude Code session for each.

## Phase 0 — Foundations

```text
Task: lay the groundwork for the inverted-index refactor of the Octavius linter.

Context. Octavius is a plain-language linter (FastAPI backend in main.py +
routes/, React frontend in frontend/, ~801 rules in published/rulebook.parquet
loaded via logic/dispatcher.py). We are starting a multi-phase refactor that
replaces the current "run every rule against every text" dispatch with a
feature-based inverted index. This phase ships ZERO behaviour change — it is
foundations only.

Branch. Create `claude/iir-phase-0-foundations` off the integration branch
`claude/inverted-index-refactor` (create the integration branch off main if it
does not yet exist). Open a PR back to the integration branch when done.

Deliverables.

1. Create `docs/REFACTOR_LOG.md` with this template:
       # Inverted-Index Refactor — Decision Log
       ## Phase 0 — Foundations (YYYY-MM-DD)
       ### Shipped
       ### Deferred
       ### Surprises
       ### Follow-ups for next phase
   Append your actual notes under each heading at the end of the phase.

2. Create `logic/features/__init__.py` and `logic/features/vocabulary.py`.
   `vocabulary.py` defines the feature vocabulary as a frozen Enum or
   `Final[frozenset[str]]`, organised by prefix (ZONE_, HAS_, LING_, PATTERN_,
   APS_, MASK_, DOC_). The exact vocabulary is supplied in REFACTOR_PLAN.md
   §2 — copy it verbatim. Add a `validate_feature(name: str)` helper that
   raises ValueError on unknown names.

3. Extend `logic/rulebook/types.py`:
   - Add `grouped_rules: list[str] | None` to `Finding` (optional, default None).
   - Add `required_features: dict[str, list[str]] | None` to `CompiledRule`
     (optional, default None — Phase 3 will populate it).
   - Add a TypedDict `FeatureRequirements` with keys `all_of`, `any_of`,
     `none_of`, each `list[str]`.

4. Extend `logic/rulebook/loader.py` to read the future `required_features`
   parquet column when present, and pass it through to `CompiledRule`. If the
   column is missing (current state), default to `None`. Do not fail.

5. Delete the stale Streamlit path:
   - Delete `app.py`, `logic/engine.py`, `logic/rules.py`,
     `octavius_component.py`, and `pages/` if it only contains Streamlit pages.
   - Update `README.md` and `CLAUDE.md` to remove references to `streamlit run
     app.py`. The runtime entry point is now `uvicorn main:app`.
   - Search the repo for any remaining imports of the deleted modules and
     either remove them or migrate them onto `logic.dispatcher`. `tests/
     test_engine.py` may need to be deleted or rewritten against the
     dispatcher — your call, document the choice.

6. Add `OCTAVIUS_DISPATCHER` env-flag plumbing to `routes/check.py`:
   - Read the env var at module load.
   - For now, both `legacy` and `indexed` resolve to `logic.dispatcher`
     (the indexed dispatcher does not exist yet). Log a warning if `indexed`
     is requested in Phase 0.
   - Add a unit test that asserts the resolution logic.

Acceptance tests.

- `pytest tests/ -v` passes.
- `uvicorn main:app` boots; `POST /check` with the original noisy example
  ("Step 1 — Merge this branch to main\nThe changes just pushed need to be on
  main before Render deploys them.") still returns its current ~33 findings
  (no behaviour change yet).
- `from logic.features.vocabulary import ZONE_PARAGRAPH, validate_feature`
  works.
- `validate_feature("NOT_A_REAL_FEATURE")` raises ValueError.
- `grep -r "streamlit" --include="*.py"` returns nothing in the runtime path
  (matches in `archive/` are fine).

Constraints. Do not implement preprocessing, the feature extractor, or the
indexed dispatcher in this phase. Foundations only.

Reporting. At the end, append to `docs/REFACTOR_LOG.md` and post a PR with a
description summarising deliverables 1–6 and any guardrails you had to bend.
```

## Phase 1 — Preprocessing layer

```text
Task: build the preprocessing layer that will feed the future feature
extractor.

Context. Phase 0 has landed. The feature vocabulary is frozen in
`logic/features/vocabulary.py` and `Finding` has `grouped_rules`. The legacy
dispatcher is unchanged. This phase adds preprocessing as a standalone module
with its own tests. It is NOT yet wired into the dispatcher — that happens in
Phase 4.

Branch. `claude/iir-phase-1-preprocessing` off
`claude/inverted-index-refactor`. PR back to integration branch.

Deliverables.

1. Add `markdown-it-py` to requirements.txt with a pinned version.

2. Create `logic/preprocess.py` exporting:
       @dataclass
       class Segment:
           kind: Literal["heading", "paragraph", "list_bullet",
                         "list_numbered", "blockquote", "code_fence",
                         "inline_code", "quoted", "table"]
           text: str
           offset: int           # char offset back into original input
           lintable: bool        # False for code_fence, inline_code, quoted

       @dataclass
       class PreprocessedDoc:
           original: str
           masked: str           # same length as original; placeholders
                                 # in masked regions
           segments: list[Segment]
           mask_map: list[tuple[int, int, str, str]]
                                 # (start, end, original, mask_kind)
           sentence_count: int
           has_structure: bool   # True iff any heading/list/fence present
           language: str         # ISO 639-1, "en" if detection unavailable

       def preprocess(text: str) -> PreprocessedDoc: ...

3. Markdown-aware segmentation. Use markdown-it-py to walk the token stream.
   Code fences and inline code emit segments with `lintable=False`.
   Blockquote content is a separate segment with `lintable=False`. Quoted
   content (paired straight or curly quotes inside paragraphs) is masked
   inline rather than split into segments — record it in mask_map with kind
   "quoted".

4. Token masking. Replace each non-prose region with a same-length run of
   the sentinel character `\uE000`. Mask kinds and patterns:
   - MASK_URL: `https?://\S+`, `www\.\S+`
   - MASK_FILEPATH: absolute (`/[a-z]+/...`) and relative (`\./...`,
     `\.\./...`) paths, `*.{py,md,ts,tsx,json,yml,yaml}` filenames
   - MASK_BRANCHNAME: `main`, `master`, `develop`, `feature/...`,
     `release/...`, `hotfix/...`
   - MASK_IDENTIFIER: snake_case_with_underscores, camelCaseTokens of
     length ≥3, dotted.identifiers
   - MASK_ENV_VAR: `[A-Z][A-Z0-9_]{2,}` not at sentence start
   - MASK_PRODUCT_NAME: `Title-Case-Hyphenated` chains of length ≥2
   - MASK_MENTION_OR_HASHTAG: `@\w+`, `#\w+`
   - MASK_CODE_SNIPPET: backticked text (already covered by inline_code
     segments), lines starting with `$ ` or `>>> `

   Each mask preserves byte offsets exactly: assert
   `len(masked) == len(original)` in tests.

5. Sentence counting. Use spaCy's sentence splitter on the unmasked
   paragraph segments (not on headings). Cache the spaCy Doc on the result
   so Phase 2 can reuse it without re-parsing.

6. Language detection. Use a lightweight method (`langdetect` or a regex
   ASCII-ratio heuristic — your call, justify in commit message). On any
   error, default to "en" and log at INFO. Do not fail.

7. Sentence-hash cache. Create `logic/sentence_cache.py`:
       class SentenceCache:
           def __init__(self, max_entries: int = 10_000): ...
           def get_or_compute(self, sentence: str,
                              compute: Callable[[str], list[Finding]]
                             ) -> list[Finding]: ...
   FIFO eviction, SHA-256 truncated to 16 hex chars as key. Process-local;
   document the lifecycle.

Tests (`tests/test_preprocess.py`).

- `test_offsets_preserved`: for 20 hand-crafted inputs, `len(masked) ==
  len(original)` and every unmasked char matches the original.
- `test_code_fence_segments_unlintable`: ```` ```python\nfoo\n``` ```` →
  one segment with kind="code_fence", lintable=False.
- `test_inline_code_masked`: a paragraph with `` `branch` `` in it has the
  backticked region in mask_map.
- `test_quoted_content_excluded`: smart and straight quotes both produce
  mask_map entries.
- `test_url_filepath_branchname_masking`: each pattern in deliverable 4
  produces the correct mask kind.
- `test_step_1_example_segments`: the noisy example from REFACTOR_PLAN.md
  produces exactly 1 paragraph segment with `lintable=True`, and `Render`,
  `main`, `branch` are in mask_map.
- `test_sentence_cache_fifo`: insert 10_001 sentences; the first one is
  evicted.
- `test_language_detection_default_en`: empty input returns "en".

Acceptance.

- `pytest tests/ -v` passes.
- `python -c "from logic.preprocess import preprocess; print(preprocess('# H\nFoo bar.\n').segments)"`
  runs.
- Latency: preprocessing a 500-word document completes in <50 ms on a
  laptop. Add a `tests/test_preprocess_perf.py` with a single timing
  assertion.

Constraints. Do not modify the dispatcher, adapters, loader, or any rule
trigger code. Preprocessing is standalone in this phase.

Reporting. Append Phase 1 entry to `docs/REFACTOR_LOG.md` (especially:
which masking edge cases you punted on). PR.
```

## Phase 2 — Feature extractor

```text
Task: build the feature extractor that maps a PreprocessedDoc to a set of
features from the frozen vocabulary.

Context. Phase 1 produced `logic/preprocess.py` with `PreprocessedDoc`.
The feature vocabulary lives in `logic/features/vocabulary.py`. This phase
implements the deterministic extractor. No rule retrieval yet — that's
Phase 4.

Branch. `claude/iir-phase-2-feature-extractor` off integration branch.

Deliverables.

1. `logic/features/extractor.py` exporting:
       @dataclass(frozen=True)
       class FeatureSet:
           document: frozenset[str]
           per_segment: list[frozenset[str]]   # aligned to doc.segments

       def extract(doc: PreprocessedDoc, nlp: spacy.Language) -> FeatureSet: ...

2. One sub-extractor module per feature family. Keep them small and
   independent:
   - `logic/features/zones.py` — ZONE_* from segment.kind.
   - `logic/features/lexical.py` — HAS_* via regex (cardinals, percent,
     currency, dates, etc.).
   - `logic/features/linguistic.py` — LING_* via spaCy (passive via
     dependency tags `nsubjpass`/`auxpass`; modals via tag_=="MD"; first/
     second person via lemma in {"i","we"}/{"you"}; imperative via root verb
     with no nsubj at sentence start; etc.).
   - `logic/features/patterns.py` — PATTERN_* multi-token regexes
     (numeric ranges `\d+\s*[-–—]\s*\d+`, regnal-numeral shape
     `\b[A-Z][a-z]+\s+(I|II|III|IV|V|VI|VII|VIII|IX|X)\b`, citation
     parentheses `\([A-Z][a-z]+,?\s+\d{4}\)`, etc.).
   - `logic/features/aps.py` — APS_* via lookup against word lists in
     `logic/features/data/`. Provide a starter wordlist for legislation
     references (load from `library_of_rules/`) and Commonwealth entities;
     leave others as empty lists with TODO markers.
   - `logic/features/mask_features.py` — MASK_* derived from
     `doc.mask_map` kinds (one feature per mask kind that appears).
   - `logic/features/document.py` — DOC_* aggregations
     (DOC_HAS_HEADINGS = any zone is heading, etc.).

3. Each sub-extractor exposes `extract(segment_text, spacy_doc) ->
   set[str]` (or `extract(doc) -> set[str]` for document-level ones).
   The orchestrator in `extractor.py` calls them and returns the
   `FeatureSet`.

4. `logic/features/extractor.py` validates every emitted feature against
   `vocabulary.validate_feature` and raises if any extractor emits an
   undeclared feature. This is a hard error — no silent typos.

5. The extractor must run on a single spaCy Doc per call (reuse
   `doc.spacy_doc` cached from Phase 1). Do not re-parse.

Tests (`tests/test_features/`).

One file per sub-extractor plus an integration test:
- `test_zones.py`: a doc with a heading and two bullet items has
  ZONE_HEADING and ZONE_LIST_BULLET in document features.
- `test_lexical.py`: 20 cases — each `HAS_*` feature gets at least one
  positive and one negative example.
- `test_linguistic.py`: passive vs active voice, imperative ("Click here")
  vs declarative, first/second person.
- `test_patterns.py`: regnal numeral fires on "Henry VIII" but NOT on
  "Step 1" once MASK_CODE_SNIPPET / MASK_IDENTIFIER neighbours are
  considered (note: the negative-feature interaction lives at the rule
  level in Phase 4, so here just verify the raw pattern).
- `test_aps.py`: at least one fixture per APS_* feature with the starter
  wordlist.
- `test_extractor_integration.py`: the noisy "Step 1 …" example produces
  the document feature set
  `{ZONE_PARAGRAPH, HAS_CARDINAL, LING_IMPERATIVE, LING_PROPER_NOUN,
    MASK_BRANCHNAME, MASK_PRODUCT_NAME, DOC_LANGUAGE_EN,
    DOC_SENTENCE_COUNT_GE_3 (false → absent)}`
  (adjust to whatever your implementation actually computes — the point
  is to lock the contract with a snapshot).
- `test_undeclared_feature_raises`: a fake sub-extractor that emits
  "ZONE_FAKE" causes `extract()` to raise.

Performance. Add `tests/test_features_perf.py` asserting that extraction
on a 500-word document completes in <100 ms.

Acceptance.

- `pytest tests/ -v` passes.
- `python -c "from logic.features.extractor import extract; ..."` smoke test.
- The integration test for the noisy example must pass before merging.

Constraints. Do not modify the dispatcher, parquet schema, or rule trigger
code. The extractor is standalone in this phase.

Reporting. Append Phase 2 entry to `docs/REFACTOR_LOG.md` — especially
any features that were *defined* in vocabulary.py but proved expensive or
unreliable to extract (mark them deferred so Phase 3's prompt doesn't ask
the LLM to require them).
```

## Phase 3 — `required_features` authoring batch

```text
Task: add a Phase 3.5 to the GitHub Actions pipeline that uses an LLM batch
to populate `required_features` for every passing rule.

Context. Phases 0–2 have shipped. The feature vocabulary is frozen and the
extractor proves which features are reliably computable. This phase emits a
new column in the working JSONL → parquet pipeline; the indexed dispatcher
in Phase 4 will read it.

Branch. `claude/iir-phase-3-feature-authoring` off integration branch.

Deliverables.

1. New script `src/extract_features.py` modelled on `src/extract_rules.py`
   and `src/correct_rules.py`. It:
   - Reads `rules_working_draft.jsonl`.
   - For each rule with `test_result == "pass"`, builds an LLM batch
     request with the prompt template in deliverable 2.
   - Submits the batch via the existing infrastructure (same client, same
     model as Phase 5 — gpt-4o-mini).
   - On collection, parses each response as JSON with keys `all_of`,
     `any_of`, `none_of`, validates every feature against
     `logic.features.vocabulary.validate_feature`, and writes back to the
     JSONL as `required_features`.
   - Rules whose response fails validation get logged with the offending
     feature and a `required_features: null` placeholder (Phase 4 falls
     back to "always retrieve" for nulls).

2. Prompt template in `prompts/features.md`. Inputs interpolated per rule:
   - rule_summary, rule_detail, taxonomy, source_url, lookup_list (if any),
     trigger_code, ui_flag, test_fire, test_no_fire.
   The prompt:
   - Lists the full feature vocabulary with one-line descriptions.
   - Asks the model to return strict JSON with `all_of` / `any_of` /
     `none_of`, citing only features from the supplied vocabulary.
   - Instructs the model to be conservative: include MASK_* features in
     `none_of` whenever the rule should not fire on identifiers, code, or
     URLs.
   - Includes 3 worked examples (regnal-number rule, passive-voice rule,
     date-format rule).

3. Two GitHub Actions workflows:
   - `.github/workflows/phase3_5_submit.yml` — submits the batch.
   - `.github/workflows/phase3_5_collect.yml` — collects results, validates,
     writes JSONL.
   Mirror the Phase 5 workflow shape and secrets.

4. Update `src/publish.py` to include `required_features` in the parquet
   schema (Arrow type: `struct<all_of: list<string>, any_of: list<string>,
   none_of: list<string>>` or three separate `list<string>` columns —
   pick whichever is cleaner with PyArrow; document the choice).

5. Update CLAUDE.md "Rulebook schema" table with the new column.

6. Run the batch and merge the resulting `rulebook.parquet` into the
   integration branch in this PR. The PR diff should include the regenerated
   parquet (LFS or direct, matching repo convention).

Tests.

- `tests/test_extract_features.py`:
  - Fixture: 5 hand-crafted rule rows.
  - Mock the LLM client to return canned JSON.
  - Assert the JSONL gets the right `required_features` and that an invalid
    feature name causes a validation error to be logged.
- `tests/test_publish_required_features.py`: round-trip a rule with all
  three slots populated through `src/publish.py` and back.

Acceptance.

- `pytest tests/ -v` passes.
- `python -c "import pyarrow.parquet as pq;
   t = pq.read_table('published/rulebook.parquet');
   print('required_features' in t.schema.names)"` returns True.
- At least 80% of passing rules have a non-null `required_features`. The
  remainder are listed in REFACTOR_LOG.md with the model's failure mode so
  we can iterate.

Constraints. Do not modify the dispatcher in this phase. Do not hand-edit
features in the JSONL (other than during your local fixture tests). All
production features come from the batch.

Reporting. Append Phase 3 entry to `docs/REFACTOR_LOG.md` with: total
rules, % validated, top 10 most-required features, top 10 most-forbidden,
any features in vocabulary.py that NO rule asked for (candidates for
removal in Phase 6).

Cost note. Estimate the batch cost in your PR description before running
it — the user wants visibility on spend.
```

## Phase 4 — Indexed dispatcher

```text
Task: build the inverted-index dispatcher and wire it behind the
OCTAVIUS_DISPATCHER env flag.

Context. Phases 0–3 have shipped. `published/rulebook.parquet` now carries
`required_features` for ~80%+ of passing rules. The legacy dispatcher is
still the default. This phase adds the new dispatch path.

Branch. `claude/iir-phase-4-indexed-dispatcher` off integration branch.

Deliverables.

1. `logic/indexed_dispatcher.py`:
       def run_rules(text: str,
                     disabled_rule_ids: set[str] | None = None,
                     disabled_taxonomies: set[str] | None = None
                    ) -> list[Finding]: ...
   Signature-compatible with the legacy dispatcher. Internally:
   a. Call `preprocess(text)`.
   b. Call `extract(doc, nlp)` to get document and per-segment features.
   c. For each lintable segment, compute the union of features (segment ∪
      document) and intersect with the inverted index to get candidate
      rule IDs.
   d. For rules with `required_features=None`, fall back to "always run"
      (preserves recall during migration).
   e. Execute candidate rules' trigger code on the segment text, translate
      offsets back via `segment.offset`, drop findings overlapping
      `mask_map` entries.
   f. Use the SentenceCache from Phase 1 to short-circuit unchanged
      sentences.
   g. Apply post-firing logic:
      - Drop document-level findings if
        `not preprocessed.has_structure or sentence_count < 3`.
      - Span deduplication: collapse exact `(start, end, rule_id)` and
        group same-span across rules into one Finding with `grouped_rules`
        populated.
      - Per-rule firing budget: cap each rule_id at 5 spanned findings
        per document; the 6th+ become a single document-level summary
        finding ("rule X fired N times — review pattern") that survives
        the document-level gating.

2. The inverted index. Build at module load by iterating the
   `CompiledRule` list:
       _INDEX_ALL_OF: dict[feature, frozenset[rule_id]]
       _INDEX_ANY_OF: dict[feature, frozenset[rule_id]]
       _INDEX_NONE_OF: dict[feature, frozenset[rule_id]]
       _UNCONSTRAINED: frozenset[rule_id]   # required_features is None
   Candidate set algorithm (per segment):
       candidates = _UNCONSTRAINED.copy()
       for f in features:
           candidates |= _INDEX_ANY_OF.get(f, frozenset())
       # all_of: rule must have ALL of its required features satisfied
       for rule in rules_with_all_of:
           if rule.all_of <= features and not (rule.none_of & features):
               candidates.add(rule.id)
   Document the algorithm in the module docstring; the above is sketch.

3. Update `routes/check.py`:
   - Read `OCTAVIUS_DISPATCHER` env var at module load.
   - Resolve to `logic.dispatcher` (legacy) or
     `logic.indexed_dispatcher` (new).
   - Default remains `legacy` in this phase.

4. Add a debug endpoint `GET /debug/explain?text=...&rule_id=...` that
   returns: extracted features, whether the rule was retrieved, and which
   feature requirement decided it. Behind the env flag
   `OCTAVIUS_DEBUG_ENDPOINTS=1`. This is the "why didn't rule X fire?"
   tool.

Tests (`tests/test_indexed_dispatcher.py`).

- `test_step_1_example_quiet`: the noisy example produces ≤6 findings
  under the indexed dispatcher (regression target).
- `test_unconstrained_rules_still_run`: a rule with
  `required_features=None` still fires on a matching input.
- `test_none_of_blocks_retrieval`: a rule with
  `none_of=[MASK_BRANCHNAME]` is not retrieved when the segment masked
  `main`.
- `test_all_of_strict`: a rule with `all_of=[LING_PASSIVE_VOICE,
  HAS_CARDINAL]` only retrieves when both are present.
- `test_firing_budget_summary`: synth input that fires one rule 10× →
  5 spanned findings + 1 summary.
- `test_span_grouping`: two rules on the same span → 1 finding with
  `grouped_rules` length 2.
- `test_document_level_gating_short_input`: 1-sentence input emits zero
  document-level findings.
- `test_legacy_parity_baseline`: run both dispatchers on a fixed corpus of
  10 documents; collect `(rule_id, start, end)` tuples; report Jaccard
  similarity. Don't assert a threshold — just print it. Phase 5 will turn
  this into a calibrated metric.

Performance.

- `tests/test_indexed_perf.py`: a 500-word document lints in <300 ms
  (cold cache) and <100 ms (warm). Document numbers in REFACTOR_LOG.md.

Acceptance.

- `pytest tests/ -v` passes.
- `OCTAVIUS_DISPATCHER=indexed uvicorn main:app` boots and the noisy
  example via `POST /check` returns ≤6 findings.
- `OCTAVIUS_DISPATCHER=legacy uvicorn main:app` returns the original ~33.

Constraints. Don't touch the parquet, the LLM pipeline, or the React
frontend in this phase. Both dispatchers must remain functional.

Reporting. Append Phase 4 entry to `docs/REFACTOR_LOG.md` with:
- Step 1 example: legacy N findings → indexed N findings.
- Latency: cold/warm.
- Jaccard parity on the 10-doc corpus.
- Any rules that retrieved on every segment despite having
  required_features (debugging hooks for Phase 5).
```

## Phase 5 — Calibration corpus + telemetry

```text
Task: build the calibration corpus, the precision-scoring harness, and the
telemetry path that will justify the Phase 6 cutover.

Context. Phases 0–4 have shipped. The indexed dispatcher works behind the
flag. We need quantitative evidence that it is at least as good as the
legacy dispatcher on real documents, not just on the Step 1 example.

Branch. `claude/iir-phase-5-calibration` off integration branch.

Deliverables.

1. `corpus/` directory in the repo root with subdirs:
   - `corpus/should_not_fire/` — 80–120 short docs (~2–6 sentences each)
     where most rules should NOT fire. Mix of:
     - 20 manually-collected real samples: README excerpts, Slack messages,
       commit messages, code comments, dev-team notes.
     - 60+ LLM-generated synthetic samples across content types
       (Slack, email, code review, ticket comment, blog intro, recipe).
       Generate via a one-off script `corpus/generate_should_not_fire.py`
       that calls the same LLM client as the pipeline. The prompt asks
       for plain English samples that reflect each content type's
       conventions. Save outputs to `corpus/should_not_fire/synthetic/`
       with a manifest JSON listing the prompt used per file.
   - `corpus/should_fire/` — 30–50 hand-crafted samples explicitly
     designed to trigger known rules (passive voice, regnal numerals,
     numeric ranges, etc.). Each file has a sidecar
     `<name>.expected.json` listing expected rule_ids.

2. `scripts/score_dispatchers.py`:
   - Loads the corpus.
   - Runs both dispatchers (legacy and indexed) over every doc.
   - For `should_not_fire/`: computes per-rule false-positive rate and
     per-doc finding count.
   - For `should_fire/`: computes per-rule recall against the expected
     set.
   - Writes a Markdown report `corpus/REPORT.md` with:
     - Headline: legacy mean findings/doc vs indexed.
     - Top 20 noisiest rules under each dispatcher.
     - Recall delta per rule between dispatchers (should be ≥0 for the
       cutover to be safe).
     - Latency p50/p95 under each dispatcher.

3. Telemetry. Add `logic/telemetry.py`:
       def log_finding_event(event: Literal["fired", "dismissed",
                                            "accepted", "not_applicable"],
                             rule_id: str, doc_hash: str,
                             features: frozenset[str]) -> None: ...
   Default sink: append-only JSONL at
   `${OCTAVIUS_TELEMETRY_DIR:-/tmp/octavius_telemetry}/events.jsonl`.
   Wire `fired` events into `logic/indexed_dispatcher.py` (one per
   finding, after dedup). The other event kinds will be triggered by the
   frontend in Phase 6.

4. `scripts/aggregate_telemetry.py` reads the telemetry JSONL and produces
   per-rule precision estimates (using accept/dismiss events; firings
   alone aren't enough). Output: `corpus/PRECISION.md`. Even with no
   user data yet, this should run on the corpus's `should_not_fire` runs
   (where every fire is treated as a synthetic dismissal) to seed
   precision priors.

Tests.

- `tests/test_score_dispatchers.py`: end-to-end on a 5-doc miniature
  corpus, asserts the report renders.
- `tests/test_telemetry.py`: log events, read them back, aggregate.

Acceptance.

- `pytest tests/ -v` passes.
- `python scripts/score_dispatchers.py` runs and produces `corpus/REPORT.md`.
- The report shows: indexed mean findings/doc on `should_not_fire/` is
  ≥ 70% lower than legacy. If not, do not proceed to Phase 6 — investigate
  and document in REFACTOR_LOG.md instead.
- Recall on `should_fire/` is ≥ 90% under indexed (ideally ~equal to
  legacy). If recall regressed, identify which `required_features` are
  too strict and either (a) loosen them in a follow-up batch, or (b) flip
  those rules' `required_features` to null.

Constraints. Do not change dispatcher logic in this phase except to add
the telemetry hook. Do not flip the default env flag — that is Phase 6.

Reporting. Append Phase 5 entry to `docs/REFACTOR_LOG.md` with the
headline numbers from REPORT.md and a go/no-go recommendation for Phase 6.
```

## Phase 6 — Frontend updates + cutover

```text
Task: update the React component for the new finding shape, flip the
default dispatcher to `indexed`, and remove the legacy code.

Context. Phases 0–5 have shipped. The indexed dispatcher meets the
acceptance bar in `corpus/REPORT.md`. The frontend still treats every
Finding identically. This phase finishes the migration.

Branch. `claude/iir-phase-6-frontend-cutover` off integration branch.

Deliverables.

1. Update `frontend/src/types.ts`:
   - Add `groupedRules?: string[]` to `Finding`.
   - Add `severity: 'error' | 'warn' | 'info' | 'hint'` (was already
     present; verify).
   - Add `documentLevel?: boolean`.

2. Update `frontend/src/components/FindingCard.tsx`:
   - When `groupedRules` has length ≥2, render a "N rules flagged this
     phrase" header with a click-to-expand list.
   - When `documentLevel` is true, render in a separate "Document-level
     suggestions" pane at the bottom of FindingsPanel rather than as an
     inline highlight (since there's no span to highlight).

3. Update `frontend/src/components/FindingsPanel.tsx` to add severity
   tier filtering: a tri-state toggle ("Errors only / Errors + warnings /
   All") with default = "Errors + warnings". Wire to a state hook.

4. Three-state per-finding action: accept / dismiss / not-applicable.
   Each click POSTs to a new `/feedback` endpoint:
   - `routes/feedback.py` exposing `POST /feedback` that takes
     `{event, rule_id, doc_hash, features}` and calls
     `logic.telemetry.log_finding_event`.
   - Wire the React buttons to the endpoint with optimistic UI.

5. Flip the default. In `routes/check.py`, change the default value of
   `OCTAVIUS_DISPATCHER` from `legacy` to `indexed`. Document the rollback
   procedure in `docs/REFACTOR_LOG.md` ("set OCTAVIUS_DISPATCHER=legacy
   and redeploy").

6. Removal sweep. Once the cutover is verified locally and on Render:
   - Delete `logic/dispatcher.py` (legacy).
   - Rename `logic/indexed_dispatcher.py` → `logic/dispatcher.py`.
   - Remove the env-flag branching from `routes/check.py`.
   - Remove any features in `logic/features/vocabulary.py` that no rule
     ever required (per the Phase 3 report).
   - Update CLAUDE.md to describe the new architecture and remove
     references to the legacy dispatcher.

Tests.

- `frontend/src/components/__tests__/FindingCard.test.tsx`: rendering
  cases for grouped findings, document-level findings, severity tiers.
- `tests/test_feedback_route.py`: POST /feedback → telemetry event
  written.
- Re-run the Phase 5 score_dispatchers script in CI as a smoke test
  (`legacy` path should still work pre-removal; remove that test case
  in the same PR as the removal sweep).

Acceptance.

- `pytest tests/ -v` passes.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.
- Manual smoke test: lint the Step 1 example through the running app,
  verify ≤6 findings rendered, with correct grouping and document-level
  separation.
- Latency: p50 <200 ms, p95 <700 ms on the corpus. Capture in
  REFACTOR_LOG.md.

Constraints. Do the frontend updates and cutover in TWO commits if
possible, so the cutover is reversible: commit 1 = frontend supports both
shapes, commit 2 = flip default and remove legacy. The PR can contain
both.

Reporting. Final REFACTOR_LOG.md entry:
- What shipped end-to-end.
- Final corpus numbers (legacy vs indexed).
- Rules quarantined / removed.
- Vocabulary features actually used vs defined.
- Open follow-ups (e.g. embedding prefilter, SLM verifier, override
  graph).
- Mark the refactor complete.

Then merge the integration branch into main.
```

---

# 4. Risks and how each prompt addresses them

| Risk | Where it surfaces | Mitigation in plan |
|---|---|---|
| Feature vocabulary is wrong / under-specified | Phase 2 / 3 | Vocabulary frozen in Phase 0; Phase 2 must error on unknown features; Phase 3 validates LLM output against it |
| LLM mis-tags `required_features`, killing recall | Phase 3 / 5 | Null fallback = "always run"; Phase 5 measures recall on `should_fire/` corpus before any cutover |
| Legacy and indexed diverge silently | Phase 4 / 5 | Both dispatchers live until Phase 6; parity report mandatory before flip |
| Latency regresses | Phase 4 / 6 | Per-phase perf tests; final p50/p95 gate in Phase 6 acceptance |
| Frontend breaks on new fields | Phase 6 | Backwards-compat fields are optional; cutover is two commits |
| Spec drift between sessions | All phases | `docs/REFACTOR_LOG.md` is mandatory output of every phase |

# 5. What you do between sessions

After each PR:
1. Read the agent's `REFACTOR_LOG.md` entry.
2. Skim the diff (especially: any guardrails the agent bent, any tests it weakened).
3. If the acceptance criteria were met, merge into `claude/inverted-index-refactor`.
4. If not, leave a review comment on the PR — Claude Code can iterate on the same branch.
5. Start the next phase's session with a fresh context window. The decision log + the merged code are sufficient handoff.

If anything in the plan looks off — particularly the feature vocabulary in §2, the corpus size in Phase 5, or the acceptance thresholds — flag it before you start Phase 0. Once Phase 0 lands, the vocabulary is hard to change without rerunning the Phase 3 batch.
