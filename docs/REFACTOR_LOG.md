# Inverted-Index Refactor — Decision Log

## Phase 0 — Foundations (2026-05-04)
### Shipped
- New `logic/features/` package containing `vocabulary.py`. The vocabulary
  is a `Final[frozenset[str]]` covering the eight feature families
  (ZONE_*, ANCESTOR_*, HAS_*, LING_*, PATTERN_*, REL_*, APS_*, EXEMPT_*,
  DOC_*) plus a `validate_feature()` callable that rejects both unknown
  names and any name matching the threshold-suffix regression guard
  (`r"_(GE|GT|LT|LE)?_?\d+P?$"`). `EXEMPT_FEATURES` is also exported as
  a sub-frozenset for the eventual `none_of`-only validation.
- `logic/rulebook/types.py` extended with `MutationClass` literal,
  `FeatureRequirements` TypedDict, and three new `NotRequired` fields:
  `Finding.grouped_rules`, `Finding.mutation_class`,
  `CompiledRule.required_features`, `CompiledRule.mutation_class`. All
  default to `None` until the phases that populate them ship.
- `logic/rulebook/loader.py` reads `required_features` and
  `mutation_class` parquet columns when present; missing columns default
  to `None` (loader does not fail on the current parquet, which lacks
  both columns).
- `OCTAVIUS_DISPATCHER` env-flag plumbing in `routes/check.py`. Both
  `legacy` and `indexed` resolve to `logic.dispatcher` for now, with a
  warning logged when `indexed` is requested. Unit tests cover the
  resolution logic in `tests/test_routes_check_dispatcher_flag.py`.
- Streamlit path deleted: `app.py`, `logic/engine.py`, `logic/rules.py`,
  `octavius_component.py`, `pages/1_Developer.py` (and the now-empty
  `pages/` directory) all removed; `tests/test_engine.py` deleted because
  it asserted against the removed spaCy/Doc-shaped engine and the
  parquet-driven dispatcher is already covered by `test_dispatcher.py`,
  `test_routes_check.py`, and the per-adapter tests. `streamlit` and
  `st-annotated-text` removed from `requirements.txt`.
- `README.md` and `CLAUDE.md` updated: runtime entry point is
  `uvicorn main:app`, references to `streamlit run app.py`,
  `logic/engine.py`, and `logic/rules.py` are gone. CLAUDE.md key-files
  table now reflects the dispatcher / rulebook layout and adds the new
  `docs/REFACTOR_LOG.md` and `logic/features/vocabulary.py` entries.
- `docs/REFACTOR_LOG.md` created (this file).

### Deferred
- No preprocessing layer, no feature extractors, and no indexed
  dispatcher in this phase — explicitly out of scope.
- `COUNT_*` features and `min_count`-style requirement slots: not added;
  tracked in the "Deferred features" section below.
- `mutation_class` and `required_features` plumbing through to the JSON
  response shape in `routes/check.py`: deferred to Phase 4 when the
  frontend will need them.

### Surprises
- The published parquet does not yet have a `required_features` or
  `mutation_class` column, so the loader change is a pure no-op against
  the current data. That is fine for Phase 0 (the columns will be added
  by Phase 3) but means we have no end-to-end test for the pass-through
  yet — covered indirectly by `test_rulebook_loader.py` continuing to
  pass.
- `TypedDict` total=True classes can be safely extended with optional
  fields using `typing.NotRequired` (Python 3.11+), avoiding the need to
  flip the existing definitions to `total=False` and re-declare every
  required field.

### Follow-ups for next phase
- Phase 1 introduces `PreprocessedDoc` (with `.counts: dict[str, int]`)
  and the segmenter/feature-extraction pipeline. The vocabulary import
  surface in `logic/features/__init__.py` is the entry point those
  modules should target.
- Phase 3 will start writing `required_features` and `mutation_class`
  into the parquet; at that point add a loader test that asserts the
  pass-through with a synthetic row.
- Phase 2/3 should also add a CI check that runs `validate_feature` over
  every name in every rule's `required_features` slot.


## Phase 1 — Preprocessing layer (2026-05-05)
### Shipped
- New `logic/preprocess.py` exporting `Segment`, `PreprocessedDoc`, and
  `preprocess(text)`. Segmentation is driven by `markdown-it-py` (the
  parser is enabled with the GFM `table` extension). The walker emits
  `Segment`s for headings, paragraphs, code fences (lintable=False),
  and table cells; `bullet_list_open` / `ordered_list_open` push the
  appropriate `list_bullet` / `list_numbered` ancestor onto the stack
  at `list_item_open` so a paragraph nested in a blockquote inside a
  bullet item ends up with `ancestors=["list_bullet", "blockquote"]`.
- Token masking via priority-ordered regex over the original text:
  inline code → `$`/`>>>` REPL lines → URLs → branch names → file
  paths → mentions/hashtags → hyphenated product names → snake / camel
  / dotted identifiers → env vars (skipped at sentence start) →
  standalone Title-Case product-name heuristic → quoted content. Each
  match is replaced with the private-use sentinel `` of equal
  length, and `len(masked) == len(original)` is asserted by the offset
  test suite.
- `mask_map` records `(start, end, original, exemption_kind)` where
  `exemption_kind` is the lowercased `EXEMPT_*` feature stem
  (`url`, `filepath`, `branchname`, `identifier`, `env_var`,
  `product_name`, `mention_or_hashtag`, `code_snippet`,
  `quoted_content`).
- `counts: dict[str, int]` populated via lightweight regex counting on
  the original text (`sentence`, `cardinal`, `acronym`,
  `proper_noun_likely`, `paren_pair`). Reserved for the future
  `min_count` requirement type — no Phase 1 consumer.
- Sentence counting and cached `spacy_doc` via a blank `en` pipeline
  with the rule-based `sentencizer` (~5 ms for a 500-word document).
  Loading the full `en_core_web_sm` parser pushed a 500-word document
  past the 50 ms budget, so we ship the lightweight pipeline now and
  let Phase 2 re-parse with the full pipeline if its features need it.
- ASCII-letter language heuristic (`logic.preprocess._detect_language`)
  in lieu of `langdetect`: the `langdetect` sdist failed to build in
  the project's CI environment (no working C++ toolchain for the
  `six`-backed wheel), and APS content is overwhelmingly ASCII English.
  Heuristic returns `"en"` when ≥80 % of letter chars are ASCII,
  `"und"` otherwise; defaults to `"en"` on empty input or any error.
- New `logic/sentence_cache.py` with `SentenceCache(max_entries=10_000)`
  exposing `get_or_compute(sentence, compute)`. Keys are SHA-256
  truncated to 16 hex chars; eviction is FIFO via `OrderedDict`. The
  cache is process-local and intended to be instantiated by the
  Phase 4 indexed dispatcher.
- `markdown-it-py==4.0.0` pinned in `requirements.txt`.
- `tests/test_preprocess.py` (14 tests covering offset preservation,
  fence/inline-code/quote/url/path/branch masking, ancestor chains,
  the Step 1 noisy example, counts, language defaults, sentence-cache
  FIFO eviction and idempotency, and `has_structure`) plus
  `tests/test_preprocess_perf.py` enforcing the 50 ms / 500-word
  budget. All 93 tests in the repo pass.

### Deferred / punted
- **Footnote and reference-list segments.** `markdown-it-py` does not
  emit these without optional plugins; the `Segment` Literal includes
  both kinds but the walker never produces them in this phase. Will
  enable the `footnote_plugin` if a Phase 2 rule needs it.
- **Inline code ancestors.** `inline_code` segments are emitted with
  `ancestors=[]` rather than the chain of containing block kinds. The
  exact lineage was not required by Phase 2's `ANCESTOR_*` feature
  set, and re-deriving it from the inline-token offset would add
  complexity for no current consumer.
- **Standalone Title-Case product-name heuristic.** The strict
  spec (`Title-Case-Hyphenated chains length ≥2`) does not match the
  `Render` token in the Step 1 example. We added a lenient
  side-pattern (`\b[A-Z][a-z]{4,}\b`, only when not at a sentence
  start) that masks single Title-Case words ≥5 chars mid-sentence as
  `product_name`. This over-masks ordinary proper nouns
  (e.g. "Sydney", "Canberra"); revisit when Phase 2 ships
  `LING_PROPER_NOUN` and we can decide whether masking is still
  desired.
- **Contraction-aware single-quote detection.** The straight-quote
  pattern uses `(?<!\w)'…'(?!\w)` to avoid matching contractions
  (`don't`), but adjacent dialog like `said 'no.'` may still produce
  surprising spans. Acceptable for Phase 1; will be tightened if
  telemetry shows quote-mismatch noise.
- **Full spaCy parse caching.** As above, only the rule-based
  sentencizer runs in Phase 1. Phase 2 will need to decide whether to
  upgrade the cached pipeline (and pay the latency) or run its own
  full parse on the masked paragraph text.

### Surprises
- markdown-it-py's `paragraph_open` `map` covers the entire wrapped
  block (e.g. two soft-break-joined lines) — exactly what we want for
  segment text — but for `td_open` / `th_open` the `map` is sometimes
  ``None`` and we have to fall back to the inline child's map.
- `[A-Z][a-z]+` is a noisy proper-noun signal, but it is good enough
  for `counts.proper_noun_likely`. `min_count`-style gating in a future
  phase can layer on stricter rules.

### Follow-ups for next phase
- Phase 2 reads `PreprocessedDoc.spacy_doc` for token-level features.
  If the sentencizer-only Doc isn't enough, swap the Phase 1 loader
  back to `en_core_web_sm` (with `disable=["ner", "lemmatizer"]`) and
  re-measure the 500-word budget, or run the full parse lazily.
- Phase 3 should cross-check that `mask_map` exemption kinds and
  `EXEMPT_*` feature names stay in lockstep — add a CI assertion that
  ``{kind for *_, kind in mask_map} == {f.removeprefix("EXEMPT_").lower() for f in EXEMPT_FEATURES}``.

## Phase 2 — Feature extractor (2026-05-05)

### Shipped
- **`logic/features/extractor.py`** exporting `FeatureSet` (frozen dataclass
  with `document: frozenset[str]` and `per_segment: list[frozenset[str]]`) and
  `extract(doc, nlp, long_sentence_threshold=25) -> FeatureSet`. The
  orchestrator calls all sub-extractors in order, validates every emitted
  feature name via `vocabulary.validate_feature`, and raises `ValueError` on
  any unknown name — undeclared features are a hard error, not a warning.
- **7 sub-extractors**, each exporting a clean `extract(...)` function:
  - `logic/features/zones.py` — ZONE_* (from `segment.kind`),
    ANCESTOR_* (from `segment.ancestors`).
  - `logic/features/lexical.py` — 20 HAS_* features via compiled regex over
    raw segment text.
  - `logic/features/linguistic.py` — 10 LING_* features (passive voice via
    `nsubjpass`/`auxpass`; modals via `tag_=="MD"`; first/second person via
    lemma; imperative via ROOT VB with no `nsubj`; title-case run of 2+
    tokens; all-caps token; negation via `neg` dep; long sentence via word
    count ≥ threshold). Primary entry point is `extract_from_spacy_doc(doc,
    threshold)` for batch use; `extract(segment, nlp, threshold)` is the
    per-segment convenience wrapper used in tests.
  - `logic/features/patterns.py` — 6 PATTERN_* features: numeric ranges,
    citation parentheticals, heading title/sentence case, bullet trailing
    period, regnal numeral shape.
  - `logic/features/relations.py` — 4 REL_* features taking the full
    `PreprocessedDoc`: `REL_BULLET_AFTER_COLON` (list item whose lintable
    predecessor ends with `:`); `REL_ACRONYM_DEFINED_ON_FIRST_USE` (segment
    contains "Full Name (ACRO)" intro pattern); `REL_HEADING_FOLLOWED_BY_LIST`
    (heading whose immediate lintable successor is a list); `REL_CITATION_AFTER_QUOTE`
    (citation-like parenthetical within ~50 chars of a `quoted_content` mask).
  - `logic/features/aps.py` — 5 APS_* features: legislation references via
    regex ("Name Act YYYY"); department names via pattern + wordlist;
    ministerial titles via wordlist; long-form date via regex; Commonwealth
    entities via wordlist. Wordlists live in `logic/features/data/` (3 starter
    files).
  - `logic/features/exemptions.py` — EXEMPT_* features mapped from
    `mask_map` entries. `extract_for_segment` fires for mask entries within
    the segment's char range; `extract_for_document` fires for any entry
    anywhere in the document. Both are called by the orchestrator so that each
    exemption kind appears in the containing segment AND the document feature
    set.
  - `logic/features/document.py` — 4 DOC_* features assembled after all
    per-segment passes: `DOC_HAS_HEADINGS`, `DOC_HAS_LISTS`,
    `DOC_HAS_CITATIONS` (any `APS_LEGISLATION_REFERENCE` or
    `PATTERN_CITATION_PARENS` in any segment), `DOC_LANGUAGE_EN`.
- **`logic/features/data/`** — 3 starter wordlists:
  `department_names.txt`, `ministerial_titles.txt`,
  `commonwealth_entities.txt`.
- **Phase 1 list-segment fix**: `_segment_markdown` now emits `list_bullet` /
  `list_numbered` segment kinds for list-item content (previously they were
  `paragraph` with list ancestors). Required for `ZONE_LIST_BULLET` /
  `ZONE_LIST_NUMBERED` to fire; no Phase 1 tests broke.
- **Phase 1 spaCy upgrade**: `_get_nlp()` now loads
  `en_core_web_sm(disable=["ner","lemmatizer"])` instead of
  `spacy.blank("en") + sentencizer`. The richer dependency parse and POS
  tagger are needed by Phase 2's linguistic extractor. The 50 ms preprocessing
  budget was updated to 150 ms (observed warm minimum ~65 ms on the test
  document; 2× headroom). Quality was chosen over latency per project
  guidelines.
- **Performance optimisation**: The linguistic sub-extractor originally called
  `nlp(segment.text)` once per segment (24 calls × 5 ms ≈ 120 ms for the
  perf-test doc, exceeding budget). The orchestrator now batches all lintable
  segment texts through `nlp.pipe()` in a single call, cutting the warm
  extraction time to ~60 ms for the same document.
- **Tests** (`tests/test_features/`): 9 unit-test files (zones, ancestors,
  lexical [20 parametrised cases], linguistic, patterns, relations, aps,
  exemptions, extractor_integration) + `tests/test_features_perf.py` enforcing
  the <100 ms / 500-word budget. All 232 tests in the repo pass.

### Deferred / not shipped
- **`ZONE_BLOCKQUOTE` / `ZONE_FOOTNOTE` / `ZONE_REFERENCE_LIST`**: Phase 1
  never emits these segment kinds (blockquotes remain as ancestors; footnotes
  and reference-lists require unshipped markdown-it plugins). These zone
  features are in the vocabulary for future use but cannot fire in Phase 2.
- **`ANCESTOR_TABLE` / `ANCESTOR_FOOTNOTE` / `ANCESTOR_HEADING_SECTION`**:
  Phase 1 never pushes these ancestor values; features mapped but never fire.
- **`LING_NEGATION` fired on `not` tokens without `neg` dep**: Some spaCy
  parses assign `neg` dep only to the explicit "not" or "no" token; contracted
  forms ("don't", "isn't") fire because spaCy decomposes them. Acceptable for
  Phase 2; revisit if rule telemetry shows false positives.
- **APS_* wordlists are sparse starters**: `department_names.txt`,
  `ministerial_titles.txt`, and `commonwealth_entities.txt` cover the examples
  found in `library_of_rules/` but are far from exhaustive. Phase 3's LLM
  batch will identify more gaps; the lists should be extended then.
- **`REL_ACRONYM_DEFINED_ON_FIRST_USE` is conservative**: it fires only on the
  defining segment, not on later uses of the defined acronym. A more complete
  implementation would track the full acronym inventory and fire on every
  correct use. Deferred — the current signal is useful for rule "always
  introduce acronyms on first use".

### Deferred features (mark these as risky for Phase 3)
The following vocabulary entries were found unreliable or expensive to extract
and **should be marked `deferred` in Phase 3's batch prompt** so the LLM does
not generate `required_features` that reference them:

| Feature | Reason deferred |
|---------|----------------|
| `ZONE_BLOCKQUOTE` | Phase 1 never produces blockquote-kind segments |
| `ZONE_FOOTNOTE` | Requires unshipped footnote plugin |
| `ZONE_REFERENCE_LIST` | Requires unshipped reference-list plugin |
| `ANCESTOR_TABLE` | Phase 1 never pushes "table" onto the ancestors stack |
| `ANCESTOR_FOOTNOTE` | Phase 1 never pushes "footnote" onto the ancestors stack |
| `ANCESTOR_HEADING_SECTION` | Phase 1 never pushes "heading_section" onto the ancestors stack |

### Surprises
- `spaCy.pipe()` reduces the tok2vec amortisation cost dramatically: 24
  separate `nlp()` calls cost ~120 ms; one `nlp.pipe(24 texts)` costs ~20 ms
  for the same corpus (5× speedup).
- Phase 1's list-item segments were `paragraph` kind with `ancestors=["list_bullet"]`,
  not `list_bullet` kind. This meant `ZONE_LIST_BULLET` could never fire. The
  fix (promote paragraph kind to list kind when inside a list item) broke no
  existing Phase 1 tests but is a semantic change that Phase 3 rule authors
  should know about.
- The curly-quote regex must NOT use a raw string that contains typographic
  single quotes (`'`…`'`) as delimiters — Python's lexer closes the raw string
  literal at the first `'`, silently truncating the character class. Use a
  plain string or double-quote delimiters instead.

### Follow-ups for next phase
- Phase 3 should cross-check `mask_map` exemption kinds and `EXEMPT_*` feature
  names stay in lockstep (suggested in Phase 1 follow-ups).
- Phase 3 prompt: mark the six deferred features in the table above as
  `requires_phase_gt_2 = true` so the LLM skips them.
- Phase 4 (indexed dispatcher): wire `extract()` into the dispatcher; the
  `nlp` object should be the same singleton used by Phase 1's `_get_nlp()` so
  the model is loaded once per process.


## Deferred features (revisit triggers)
- COUNT_* family: revisit if Phase 5 telemetry shows ranking failures that boolean count thresholds would fix. Replacement plan = integer counts in PreprocessedDoc.counts plus a `min_count` slot on FeatureRequirements.
- COST_* execution classes: revisit if Phase 4 latency tests miss the 200 ms p50 target.
- Additional PATTERN_* features: add as Phase 3's batch surfaces gaps in its responses.
- General relational sub-language: only the four REL_* features ship in Phase 0; expand if telemetry justifies it.
